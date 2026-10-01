from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from app.models.payment import PaymentStatus
from app.schemas.notification import NotificationResponse


class PaymentResponse(BaseModel):
    id: int
    ip_name: str
    tenant_name: str
    invoice_date: date
    due_date: date
    paid_at: Optional[datetime] = None
    status: PaymentStatus
    period: str
    amount: Optional[int] = None
    paid_amount: Optional[int] = None
    invoice_id: Optional[str] = None
    counterparty_id: Optional[str] = None
    # "rent"/"utilities"/"operations"/"signage"/"assp", через запятую если счёт
    # содержит строки нескольких типов, "unknown" если не распознано, None если
    # ещё не досинхронизировано (см. app/services/invoice_service_type.py).
    service_type: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class PaymentWithNotifications(PaymentResponse):
    notifications: List[NotificationResponse] = []


class PaymentFilter(BaseModel):
    period: Optional[str] = None  # YYYY-MM
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    ip_name: Optional[str] = None
    tenant_name: Optional[str] = None
    status: Optional[PaymentStatus] = None
    # "rent"/"utilities"/"operations"/"signage"/"assp" — фильтр по типу счёта
    # (колонка TenantPayment.service_type). Матчится по подстроке, чтобы счёт
    # с несколькими типами ("rent,utilities") находился по любому из них.
    service_type: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=10000)


class PaymentListResponse(BaseModel):
    items: List[PaymentWithNotifications]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaymentAnalytics(BaseModel):
    total_tenants: int
    total_invoices: Optional[int] = None
    paid: int
    partial: int = 0
    unpaid: int
    overdue: int
    # xlsx-строки, где источник (paid/остаток) сам был битой формулой (см.
    # PaymentStatus.NEEDS_REVIEW) — не лумпуется в unpaid, см.
    # PaymentService.get_payment_analytics. 0 для 1С-источников — там этот
    # статус никогда не производится.
    needs_review: int = 0
    source: Optional[str] = None
    # Какие service_type реально встречаются хоть в одном счёте текущего
    # периода/тенанта (независимо от выбранного filters.service_type —
    # иначе выбор одного типа скрыл бы все остальные из этого списка при
    # следующем перерасчёте). Нужно фронту, чтобы не показывать в фильтре
    # длинный хвост (вывеска/АССП/долг/прочее), которого в этом периоде
    # просто нет — см. InvoiceRegistryTable.tsx. Пустой список — не
    # вычислено (test-mode/live-1С ветки) или правда пусто.
    service_types_present: List[str] = []
