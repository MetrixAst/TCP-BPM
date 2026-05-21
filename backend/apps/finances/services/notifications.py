"""
Сервис доставки счетов — email и мессенджеры.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_invoice_via_email(invoice) -> bool:
    """
    Отправляет счёт по email.

    Получатель определяется так:
    1. tenant.user.email (если счёт привязан к арендатору)
    2. counterparty.email (если есть поле email у контрагента)
    3. Fallback — логируется предупреждение, письмо не отправляется.

    После успешной отправки обновляет:
        invoice.status   = 'sent'
        invoice.sent_via = 'email'
        invoice.sent_at  = now()
    и сохраняет объект.

    Возвращает True при успехе, False при ошибке.
    """
    recipient = _resolve_recipient_email(invoice)

    if not recipient:
        logger.warning(
            f"invoice_email_no_recipient: invoice_id={invoice.pk} number={invoice.number}"
        )
        return False

    try:
        subject = f"Счёт №{invoice.number}"
        body_html = render_to_string(
            'finances/email/invoice.html',
            {'invoice': invoice, 'items': invoice.items.all()},
        )
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

        msg = EmailMessage(
            subject=subject,
            body=body_html,
            from_email=from_email,
            to=[recipient],
        )
        msg.content_subtype = 'html'
        msg.send()

        _mark_sent(invoice, 'email')

        logger.info(
            f"invoice_email_sent: invoice_id={invoice.pk} number={invoice.number} to={recipient}"
        )
        return True

    except Exception as exc:
        logger.exception(
            f"invoice_email_error: invoice_id={invoice.pk} number={invoice.number} error={exc}"
        )
        return False


def send_invoice_via_messenger(invoice, channel: str) -> bool:
    """
    Заглушка отправки через мессенджер (WhatsApp / Telegram).

    Логирует факт отправки, обновляет статус и сохраняет объект.
    Возвращает True.
    """
    _mark_sent(invoice, channel)

    logger.info(
        f"invoice_messenger_stub: invoice_id={invoice.pk} number={invoice.number} "
        f"channel={channel}"
    )
    return True


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_recipient_email(invoice) -> str | None:
    """Возвращает email получателя или None."""
    if invoice.tenant_id:
        tenant = invoice.tenant
        if hasattr(tenant, 'user') and tenant.user and tenant.user.email:
            return tenant.user.email
        if hasattr(tenant, 'email') and tenant.email:
            return tenant.email

    if invoice.counterparty_id:
        cp = invoice.counterparty
        if hasattr(cp, 'email') and cp.email:
            return cp.email

    return None


def _mark_sent(invoice, channel: str) -> None:
    """Обновляет статус счёта после отправки."""
    from finances.models import GeneratedInvoice

    invoice.sent_via = channel
    invoice.sent_at  = timezone.now()
    invoice.status   = GeneratedInvoice.Status.SENT
    invoice.save(update_fields=['status', 'sent_via', 'sent_at', 'updated_at'])
