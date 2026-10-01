from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from app.models.notification import Notification, NotificationStatus
from app.schemas.notification import NotificationCreate, NotificationSend
import logging

logger = logging.getLogger(__name__)



class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def get_notifications_by_payment(self, payment_id: int) -> List[Notification]:

        return self.db.query(Notification).filter(
            Notification.payment_id == payment_id
        ).order_by(Notification.sent_at.desc()).all()

    def get_notifications_by_payments(
        self, payment_ids: Sequence[int]
    ) -> Dict[int, List[Notification]]:
        """Уведомления сразу для нескольких платежей — один запрос вместо одного
        на каждый payment_id (см. GET /api/payments, ранее было N+1)."""
        if not payment_ids:
            return {}
        rows = (
            self.db.query(Notification)
            .filter(Notification.payment_id.in_(payment_ids))
            .order_by(Notification.payment_id, Notification.sent_at.desc())
            .all()
        )
        grouped: Dict[int, List[Notification]] = {}
        for row in rows:
            grouped.setdefault(row.payment_id, []).append(row)
        return grouped

    def create_notification(self, data: NotificationCreate) -> Notification:

        notification = Notification(
            payment_id=data.payment_id,
            notification_type=data.notification_type,
            status=NotificationStatus.SENT,
            phone_number=data.phone_number
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def send_notification(
        self,
        data: NotificationSend,
        file_path: Optional[str] = None,
        tenant_id: Optional[int] = None,
        counterparty_name: Optional[str] = None,
        *,
        immediate: bool = False,
        defer_whatsapp: bool = False,
    ) -> Tuple[Notification, bool]:

        notification = Notification(
            payment_id=data.payment_id,
            notification_type=data.notification_type,
            status=NotificationStatus.SENT,
            phone_number=data.phone_number,
            sent_at=datetime.utcnow()
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)

        if defer_whatsapp:
            return notification, False

        from app.core.config import settings
        from app.services.job_queue import enqueue_whatsapp_job
        from app.services.whatsapp_jobs import deliver_notification

        job_payload = {
            "notification_id": notification.id,
            "tenant_id": tenant_id,
            "payment_id": notification.payment_id,
            "file_path": file_path,
            "counterparty_name": counterparty_name,
            "invoice_id": getattr(data, "invoice_id", None),
            "counterparty_id": getattr(data, "counterparty_id", None),
            "service_type": getattr(data, "service_type", None),
        }
        if (
            not immediate
            and settings.KAFKA_ENABLED
            and enqueue_whatsapp_job(job_payload)
        ):
            logger.info(
                "Notification %s queued to Kafka (WhatsApp)",
                notification.id,
            )
            return notification, True

        deliver_notification(
            self.db,
            notification_id=notification.id,
            tenant_id=tenant_id,
            file_path=file_path,
            counterparty_name=counterparty_name,
            service_type=getattr(data, "service_type", None),
            invoice_id=getattr(data, "invoice_id", None),
        )
        self.db.refresh(notification)
        return notification, False
    
    # mark_as_delivered/mark_as_read удалены — не было ни одного вызывающего
    # кроме собственных /delivered и /read эндпоинтов (тоже удалены). Реальная
    # простановка delivered_at происходит автоматически в whatsapp_jobs при
    # успешной отправке, а read (подтверждение прочтения) у нас никогда не
    # было источника данных для этого — Green API webhook не обрабатывается.

