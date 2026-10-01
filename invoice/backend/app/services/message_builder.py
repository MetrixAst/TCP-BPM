"""Сборка текста WhatsApp по шаблону из админки (арендатор → ТРЦ)."""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.notification import NotificationType
from app.models.payment import TenantPayment
from app.services.invoice_report import _MONTHS_RU_NOM
from app.services.tenant_1c import get_tenant_by_id
from app.services.tenant_whatsapp import get_trc_for_tenant

_SERVICE_TYPE_LABELS = {
    "rent": "Аренда",
    "utilities": "Коммунальные услуги",
    "operations": "Эксплуатация и маркетинг",
    "signage": "Вывеска",
    "assp": "АССП",
    "debt": "Долг пред. периода",
    "other": "Прочее",
}


def service_type_label(service_type: Optional[str]) -> str:
    key = (service_type or "").strip().lower()
    return _SERVICE_TYPE_LABELS.get(key, "")


def _shift_period(period: str, months: int) -> str:
    """period: 'YYYY-MM'. Returns the shifted 'YYYY-MM' string, unchanged
    if it doesn't parse."""
    try:
        year_s, month_s = period.split("-")
        year, month = int(year_s), int(month_s)
    except (ValueError, AttributeError):
        return period
    month0 = month - 1 + months
    year += month0 // 12
    month = month0 % 12 + 1
    return f"{year:04d}-{month:02d}"


def _period_month_name(period: str) -> str:
    try:
        year_s, month_s = period.split("-")
        return f"{_MONTHS_RU_NOM[int(month_s)]} {year_s}"
    except (ValueError, IndexError, AttributeError):
        return period


def _advance_billed(service_type: Optional[str], tenant) -> bool:
    """Real gap found 2026-09-02: this WhatsApp message text showed the
    invoice's raw period/month (e.g. "Период: 2026-09", "за Август") even
    for rent, while the PDF (invoice_report.py's own
    _item_name_with_payment_month) has shown the +1-shifted month ("за
    Октябрь") since the same-day fix earlier — rent is billed in advance
    for next month, same rule, just never applied to this separate text
    path before. Operations/marketing only shift for tenants with
    Tenant.invoice_operations_advance_billing=True (Maxi Mall/Astranium) —
    everyone else keeps "по факту", same split as the PDF."""
    key = (service_type or "").strip().lower()
    if key == "rent":
        return True
    if key == "operations":
        return bool(getattr(tenant, "invoice_operations_advance_billing", False))
    return False


def _display_period(payment: Optional[TenantPayment], service_type: Optional[str], tenant) -> str:
    if not payment or not payment.period:
        return payment.period if payment else ""
    if _advance_billed(service_type, tenant):
        return _shift_period(payment.period, 1)
    return payment.period


def build_whatsapp_message(
    db: Session,
    *,
    tenant_id: Optional[int] = None,
    payment_id: Optional[int] = None,
    notification_type: Optional[NotificationType] = None,
    counterparty_name: Optional[str] = None,
    invoice_number: Optional[str] = None,
    service_type: Optional[str] = None,
) -> str:
    trc = get_trc_for_tenant(db, tenant_id)
    tenant = get_tenant_by_id(db, tenant_id)
    payment = (
        db.query(TenantPayment).filter(TenantPayment.id == payment_id).first()
        if payment_id
        else None
    )

    trc_name = trc.name if trc else (tenant.name if tenant else "ТРЦ")
    tenant_name = tenant.name if tenant else (payment.tenant_name if payment else "")
    cp_name = counterparty_name or (payment.tenant_name if payment else "")
    inv_no = invoice_number or (payment.invoice_id if payment else "")
    svc_label = service_type_label(service_type)

    details = ""
    display_period = _display_period(payment, service_type, tenant) if payment else ""
    if payment:
        amount_str = str(payment.amount) if payment.amount else "0"
        due_date_str = payment.due_date.strftime("%d.%m.%Y")
        ntype = notification_type or NotificationType.OVERDUE
        service_line = f"Услуга: {svc_label}\n" if svc_label else ""
        if ntype == NotificationType.WEEK_BEFORE:
            details = (
                f"{service_line}Период: {display_period}\nСумма: {amount_str} тг\n"
                f"Крайний срок оплаты: {due_date_str}"
            )
        elif ntype == NotificationType.THREE_DAYS:
            details = (
                f"{service_line}Период: {display_period}\nСумма: {amount_str} тг\n"
                f"Крайний срок оплаты: {due_date_str}"
            )
        elif ntype == NotificationType.SAME_DAY:
            details = (
                f"{service_line}Период: {display_period}\nСумма: {amount_str} тг\n"
                f"Сегодня последний день для оплаты"
            )
        elif ntype == NotificationType.OVERDUE:
            details = (
                f"{service_line}Период: {display_period}\nСумма: {amount_str} тг\n"
                f"Крайний срок оплаты: {due_date_str}"
            )
        else:
            details = f"{service_line}Период: {display_period}\nСумма: {amount_str} тг"
    elif inv_no:
        details = f"Счёт № {inv_no}"
        if svc_label:
            details = f"Услуга: {svc_label}\n{details}"

    template = ""
    if tenant and (tenant.message_template or "").strip():
        template = tenant.message_template.strip()
    elif trc and (trc.message_template or "").strip():
        template = trc.message_template.strip()

    if template:
        replacements = {
            "{trc_name}": trc_name,
            "{tenant_name}": tenant_name,
            "{counterparty_name}": cp_name,
            "{details}": details,
            "{period}": display_period,
            # Real gap found 2026-09-02 (Maxi Mall's own custom template
            # hardcoded a literal month name — "за Август" — since there
            # was never a dynamic placeholder for it): month name of the
            # (already-shifted, where applicable) billing period, e.g.
            # "Октябрь 2026" — use this instead of retyping the month by
            # hand every period.
            "{period_month_name}": _period_month_name(display_period) if payment else "",
            "{amount}": str(payment.amount) if payment and payment.amount else "0",
            "{due_date}": payment.due_date.strftime("%d.%m.%Y") if payment else "",
            "{invoice_number}": inv_no or "",
            "{service_type}": svc_label,
            "{service_type_label}": svc_label,
        }
        message = template
        for key, val in replacements.items():
            message = message.replace(key, val or "")
        return clean_whatsapp_message(message, fallback_trc_name=trc_name)

    greeting = "Добрый день!"
    if svc_label:
        main_text = (
            f"Направляем вам счёт на оплату ({svc_label}). "
            "Подробности в приложенном документе."
        )
    else:
        main_text = "Направляем вам счёт на оплату. Подробности в приложенном документе."
    closing = f"С уважением,\n{trc_name}"
    if details:
        message = f"{greeting}\n\n{main_text}\n\n{details}\n\n{closing}"
    else:
        message = f"{greeting}\n\n{main_text}\n\n{closing}"
    return clean_whatsapp_message(message, fallback_trc_name=trc_name)


def clean_whatsapp_message(text: str, fallback_trc_name: str = "ТРЦ") -> str:
    if not text or not text.strip():
        return (
            f"Добрый день!\n\n"
            f"Направляем вам счёт на оплату. Подробности в приложенном документе.\n\n"
            f"С уважением,\n{fallback_trc_name}"
        )

    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("—", "-").replace("–", "-")
    text = text.replace(""", '"').replace(""", '"')
    text = text.replace("'", "'").replace("'", "'")
    text = text.replace("•", "-").replace("·", "-")
    # Не вырезаем кириллицу и фигурные скобки уже подставлены
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > 4096:
        text = text[:4090] + "..."
    return text
