from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.database import Base


class CounterpartyCache(Base):
    """Снимок контрагентов из 1С по арендатору (ответ API без latestInvoice)."""

    __tablename__ = "counterparty_cache"

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    data = Column(JSONB, nullable=True)
    total_from_1c = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="idle", index=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
