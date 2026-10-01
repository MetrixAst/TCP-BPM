from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class NotificationType(str, enum.Enum):
    WEEK_BEFORE = "week_before"
    THREE_DAYS = "three_days"
    SAME_DAY = "same_day"
    OVERDUE = "overdue"


class NotificationStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    # Green API вернул неуспех (после ретраев на транспортном уровне в
    # whatsapp_service) либо очередь Kafka исчерпала попытки — см.
    # whatsapp_jobs.deliver_notification и app/workers/kafka_worker.py.
    # До этого поля "не пришло" от "пока не подтверждено" в БД было не отличить —
    # status оставался SENT навсегда. Фронтенд, не знающий значения "failed",
    # не ломается: там строковое сравнение без exhaustive-match
    # (invoice-client/lib/notificationHelpers.ts).
    FAILED = "failed"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("tenant_payments.id"), nullable=False, index=True)
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    status = Column(SQLEnum(NotificationStatus), nullable=False, default=NotificationStatus.SENT)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    # Настоящее webhook-подтверждение доставки WhatsApp (см.
    # whatsapp_jobs._process_green_api_webhook, сопоставляется по
    # green_api_id_message) — до 2026-09-10 такого подтверждения не было
    # вообще: этот столбец проставлялся оптимистично сразу по факту успешного
    # HTTP-ответа Green API на отправку, что путало "принято в очередь
    # Green API" с "реально дошло до получателя" (реальный инцидент
    # 2026-09-09: 104 из 111 счетов должникам показывали "delivered" в
    # нашей БД, хотя WhatsApp реально ничего не доставил — инстанс словил
    # временную блокировку).
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    phone_number = Column(String, nullable=True)
    # idMessage, который Green API вернул на отправку — нужен, чтобы
    # сопоставить эту Notification с последующим outgoingMessageStatus
    # вебхуком (delivered/read/failed/noAccount/suspended) и узнать, что
    # реально произошло с сообщением, а не только что мы его отправили.
    green_api_id_message = Column(String, nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    

    payment = relationship("TenantPayment", back_populates="notifications")
