from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.database import Base


class AutoNotificationLog(Base):


    __tablename__ = "auto_notification_logs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "invoice_id",
            "service_type",
            "trigger_kind",
            name="uq_auto_notify_once",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    counterparty_id = Column(String(64), nullable=False)
    invoice_id = Column(String(64), nullable=False)
    service_type = Column(String(16), nullable=False)
    trigger_kind = Column(String(32), nullable=False)
    phone_number = Column(String(32), nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
