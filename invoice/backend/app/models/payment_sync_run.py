from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.db.database import Base


class PaymentSyncRun(Base):
    __tablename__ = "payment_sync_runs"

    tenant_id = Column(Integer, primary_key=True, nullable=False, default=0)
    period = Column(String(7), primary_key=True, nullable=False)
    status = Column(String(20), nullable=False, index=True)
    error = Column(Text, nullable=True)
    records = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
