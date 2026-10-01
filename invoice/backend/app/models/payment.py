from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class PaymentStatus(str, enum.Enum):
    PAID = "paid"
    PARTIAL = "partial"
    UNPAID = "unpaid"
    OVERDUE = "overdue"
    # xlsx-import-only (см. xlsx_import/normalize.py._status) — источник
    # (paid/остаток в файле) сам по себе битый (формула-ошибка типа #REF!),
    # 0 там значит "неизвестно", не "оплачено"/"не оплачено". 1С-путь этот
    # статус никогда не производит. Обрабатывать как overdue: доверять
    # сохранённому значению, а не пересчитывать по сумме покрытия — см.
    # PaymentService._row_coverage_status и analytics-цикл в get_payments.
    NEEDS_REVIEW = "needs_review"


class TenantPayment(Base):
    __tablename__ = "tenant_payments"

    id = Column(Integer, primary_key=True, index=True)
    # Настоящий внешний ключ на арендатора — до 2026-08-25 изоляция между
    # арендаторами держалась только на сравнении ip_name с tenant.legal_name
    # (свободный текст, не уникален на уровне БД), что давало утечку/
    # перезапись чужих строк при совпадении/похожести имени (см. аудит от
    # 2026-08-25 и миграцию b0c1d2e3f4a5). Nullable — исторические строки,
    # которые backfill не смог однозначно сопоставить (0 в проверенных
    # окружениях, но не исключено на другой БД), либо легаси-sync без
    # конкретного арендатора; такие строки не видны через tenant_id-scoped
    # запросы, пока не будут сопоставлены вручную — это осознанный компромисс
    # в пользу "лучше скрыть, чем утечь".
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    ip_name = Column(String, nullable=False, index=True)
    tenant_name = Column(String, nullable=False, index=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    status = Column(SQLEnum(PaymentStatus), nullable=False, index=True)
    period = Column(String, nullable=False, index=True)
    amount = Column(Integer, nullable=True)
    # Сколько реально поступило по счёту (из 1С) — используется вместе с amount,
    # чтобы отличать "оплачено частично" от "оплачено полностью" (см.
    # payment_status_rules.paid_enough). NULL — нет данных об оплате вообще.
    paid_amount = Column(Integer, nullable=True)
    invoice_id = Column(String, nullable=True, index=True)
    counterparty_id = Column(String(64), nullable=True, index=True)
    # Тип(ы) счёта из строк 1С — "rent"/"utilities"/"operations"/"signage"/"assp",
    # через запятую если счёт содержит строки нескольких типов сразу, "unknown"
    # если не распознано. Вычисляется в sync_from_1c (см.
    # invoice_service_type.resolve_invoice_service_types); NULL — строка создана
    # до появления этого поля и ещё не досинхронизирована.
    service_type = Column(String(64), nullable=True, index=True)
    # "one_c" (дефолт/бэкофилл, см. миграцию) или "xlsx" — см.
    # app/services/xlsx_import/. Раньше провенанс не хранился нигде вообще —
    # нельзя было объяснить в UI/логах, откуда взялась строка (см. аудит
    # утечки TRC от 2026-08-26, где это отсутствие провенанса мешало
    # разобраться, что показывает "1С не подключена" + ненулевые счётчики).
    source = Column(String(16), nullable=False, default="one_c", server_default="one_c")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    

    notifications = relationship("Notification", back_populates="payment", cascade="all, delete-orphan")
