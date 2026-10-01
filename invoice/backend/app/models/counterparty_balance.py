"""Снимок BUH balance по контрагенту (debit/credit), отдельно от счетов."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.sql import func

from app.db.database import Base


class CounterpartyBalance(Base):
    """
    Взаиморасчёты из onec.buh.balance → by_counterparty.
    debit = нам должны (1210), credit = аванс/мы должны (3510).
    """

    __tablename__ = "counterparty_balances"

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    # lower-case guid из 1С
    counterparty_id = Column(String(64), primary_key=True, nullable=False)
    counterparty_name = Column(String(512), nullable=True)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    # onec.buh.balance → aging: разбивка долга по срокам просрочки. На части
    # организаций (118/119/127 по BUH-API-reference) субконто "Документы расчётов"
    # не ведётся, поэтому весь долг или его часть закономерно попадает в
    # aging_unknown — это не баг парсинга, а ограничение исходных данных 1С.
    aging_current = Column(Numeric(18, 2), nullable=True)
    aging_30 = Column(Numeric(18, 2), nullable=True)
    aging_60 = Column(Numeric(18, 2), nullable=True)
    aging_90 = Column(Numeric(18, 2), nullable=True)
    aging_over120 = Column(Numeric(18, 2), nullable=True)
    aging_unknown = Column(Numeric(18, 2), nullable=True)
    aging_total = Column(Numeric(18, 2), nullable=True)
    # "one_c" (дефолт/бэкофилл) или "xlsx" — см. app/services/xlsx_import/balances.py.
    # replace_balances_for_tenant() (1С-синк) не трогает/не перезаписывает
    # xlsx-строки — иначе очередной часовой синк тихо стёр бы посчитанное
    # из excel (аудит от 2026-08-26, тот же паттерн, что и source на
    # TenantPayment).
    source = Column(String(16), nullable=False, default="one_c", server_default="one_c")
    synced_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
