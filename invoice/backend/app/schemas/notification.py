from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from app.models.notification import NotificationType, NotificationStatus


class NotificationResponse(BaseModel):
    id: int
    payment_id: int
    notification_type: NotificationType
    status: NotificationStatus
    sent_at: datetime
    delivered_at: Optional[datetime] = None
    phone_number: Optional[str] = None
    queued: bool = Field(
        False,
        description="True если WhatsApp поставлен в очередь Kafka (статус delivered придёт позже)",
    )
    whatsapp_sent: bool = Field(
        False,
        description="True если Green API принял сообщение (синхронная отправка); при queued всегда false",
    )

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    payment_id: int
    notification_type: NotificationType
    phone_number: Optional[str] = None


class NotificationSend(BaseModel):
    payment_id: Optional[int] = None
    notification_type: NotificationType
    phone_number: str = Field(..., description="Phone number for WhatsApp")
    counterparty_id: Optional[str] = Field(
        None, description="UUID контрагента из 1С — счёт и проверка телефона"
    )
    invoice_id: Optional[str] = Field(
        None, description="UUID счёта из 1С; если пусто — последний счёт контрагента"
    )
    service_type: Optional[str] = Field(
        None,
        description="rent | utilities | operations — подобрать счёт по строкам 1С",
    )


class BulkDebtorNotifyRequest(BaseModel):
    period: Optional[str] = Field(None, description="YYYY-MM")
    date_from: Optional[str] = Field(None, description="YYYY-MM-DD")
    date_to: Optional[str] = Field(None, description="YYYY-MM-DD")
    counterparty_id: Optional[str] = Field(
        None,
        description=(
            "Ограничить рассылку одним контрагентом (UUID из 1С) — для кнопки "
            "«Отправить все счета» на карточке контрагента. Пусто/не задано — "
            "как раньше, всем должникам арендатора за период."
        ),
    )
    ignore_balance_filter: bool = Field(
        False,
        description=(
            "Не резать по net (долг−аванс) из баланса 1С — слать всем со статусом "
            "unpaid/overdue за период, даже если 1С показывает аванс. Явный опт-ин "
            "оператора, по умолчанию выключен."
        ),
    )
    service_types: Optional[List[str]] = Field(
        None,
        description=(
            "Ограничить рассылку выбранными типами счёта (rent/utilities/operations). "
            "Пусто/не задано — слать по всем типам, найденным в строках счёта (как раньше)."
        ),
    )
    force: bool = Field(
        False,
        description=(
            "Явный опт-ин: переотправить, даже если на сегодня по этому счёту/типу "
            "услуги уже был занят слот (например, предыдущая попытка упала из-за "
            "неоплаченного провайдера и не была снята автоматически). Снимает "
            "старую резервацию за сегодня перед повторной отправкой. UI сейчас этот "
            "флаг не выставляет — используется только вручную при сбоях."
        ),
    )


class BulkDebtorNotifyResponse(BaseModel):
    queued: int = 0
    skipped_no_phone: int = 0
    skipped_no_service: int = 0
    skipped_service_type_filtered: int = Field(
        0,
        description="В счёте есть услуги, но ни одна не входит в выбранный фильтр типов — пропущено",
    )
    skipped_no_invoice: int = 0
    skipped_no_debt: int = 0
    skipped_duplicate: int = Field(
        0, description="Уже отправлено этому счёту/типу услуги сегодня массовой рассылкой — пропущено"
    )
    debtor_invoices: int = 0
    errors: int = 0
    message: str = ""


class XlsxBulkNotifyRequest(BaseModel):
    """Массовая рассылка счетов, загруженных из Excel (TenantPayment
    source="xlsx") — отдельная от BulkDebtorNotifyRequest модель на
    отдельном эндпоинте (app/api/notifications.py:send_xlsx_invoices_bulk),
    чтобы не трогать 1С-путь ради этого. Не режет по статусу оплаты (это
    рассылка счетов за период, не напоминание должникам) — амаунт=0/None
    пропускается автоматически, отправлять нечего."""

    period: str = Field(..., description="YYYY-MM — какой месяц из экселя рассылать")
    service_type: Optional[str] = Field(
        None,
        description=(
            "Ограничить одним типом начисления (rent/utilities/debt/other). "
            "Пусто — все типы, что есть в файле за этот период."
        ),
    )
    counterparty_id: Optional[str] = Field(
        None, description="Ограничить одним контрагентом — как в BulkDebtorNotifyRequest"
    )
    force: bool = Field(
        False,
        description="Переотправить, даже если на сегодня уже был занят слот по этой строке",
    )


class XlsxBulkNotifyResponse(BaseModel):
    queued: int = 0
    skipped_no_phone: int = 0
    skipped_no_amount: int = 0
    skipped_missing_requisites: int = Field(
        0, description="Нет банковских реквизитов у арендатора — PDF не сформировать"
    )
    skipped_duplicate: int = 0
    candidates: int = 0
    errors: int = 0
    message: str = ""


class XlsxBulkNotifyPreviewRow(BaseModel):
    tenant_name: Optional[str] = None
    counterparty_id: str = ""
    amount: Optional[float] = None
    period: str = ""
    service_type: str = ""
    reason: str = Field(
        ...,
        description="no_amount | no_phone | duplicate | missing_requisites — почему эта строка не уйдёт",
    )


class XlsxBulkNotifyPreviewResponse(BaseModel):
    """Ответ dry-run — POST /send-xlsx-invoices с dry_run=true. Ничего не
    отправляет и не резервирует слот идемпотентности (см.
    xlsx_bulk_notify_service.preview_xlsx_invoice_notifications) — реальный
    запуск сразу после preview увидит те же кандидаты, не "уже отправлено"."""

    would_queue: int = 0
    skipped_no_phone: int = 0
    skipped_no_amount: int = 0
    skipped_missing_requisites: int = 0
    skipped_duplicate: int = 0
    candidates: int = 0
    skipped_rows: List[XlsxBulkNotifyPreviewRow] = Field(default_factory=list)
    message: str = ""


class InvoiceEmailSendRequest(BaseModel):
    counterparty_id: str = Field(..., min_length=1, description="UUID контрагента из 1С")
    email: Optional[str] = Field(
        None, description="Email получателя; если пусто — email контрагента из 1С"
    )
    invoice_id: Optional[str] = Field(None, description="UUID счёта; если пусто — по типу услуги")
    service_type: Optional[str] = Field(
        None, description="rent | utilities | operations — подобрать счёт"
    )
    counterparty_name: Optional[str] = None


class InvoiceEmailSendResponse(BaseModel):
    ok: bool
    message: str = ""
    email: Optional[str] = None
    invoice_id: Optional[str] = None


class WhatsAppLogEntry(BaseModel):
    source: str = Field(..., description="manual (ручная/массовая, из Notification) | auto (из AutoNotificationLog)")
    sent_at: datetime
    phone_number: Optional[str] = None
    counterparty_name: Optional[str] = None
    ip_name: Optional[str] = None
    invoice_id: Optional[str] = None
    notification_type: Optional[str] = None
    service_type: Optional[str] = None
    status: Optional[str] = Field(
        None, description="sent/delivered/read — только для source=manual, всегда null для auto"
    )


class WhatsAppLogResponse(BaseModel):
    items: list[WhatsAppLogEntry]
    total: int


class MessagePreviewResponse(BaseModel):
    message: str = Field(
        ..., description="Ровно тот текст, что build_whatsapp_message() построил бы для реальной отправки"
    )


class QuickMessageSendRequest(BaseModel):
    """Свободный текст без счёта/PDF — быстрые шаблоны со страницы
    контрагента (шаблоны редактируются на клиенте, см. lib/quickMessageTemplates.ts;
    сюда приходит уже готовый текст с подставленными плейсхолдерами)."""

    counterparty_id: str = Field(..., description="UUID контрагента из 1С — только для проверки телефона")
    phone_number: str
    message: str = Field(..., min_length=1, max_length=4096)


class QuickMessageSendResponse(BaseModel):
    success: bool
    error: Optional[str] = None
