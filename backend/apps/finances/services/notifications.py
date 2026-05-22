import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def _render_invoice_pdf(invoice) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError("weasyprint не установлен.")

    html_string = render_to_string(
        "site/finances/invoice_pdf.html",
        {"invoice": invoice, "items": invoice.items.all()},
    )
    pdf_bytes = HTML(string=html_string, base_url=settings.BASE_DIR).write_pdf()
    return pdf_bytes


def send_invoice_via_email(invoice, recipient_email: str | None = None) -> bool:
    if not recipient_email:
        if invoice.tenant and getattr(invoice.tenant, "email", None):
            recipient_email = invoice.tenant.email
        elif invoice.counterparty and getattr(invoice.counterparty, "email", None):
            recipient_email = invoice.counterparty.email
        else:
            raise ValueError(
                f"Не удалось определить email получателя для счёта №{invoice.number}"
            )

    try:
        pdf_bytes = _render_invoice_pdf(invoice)
    except Exception as exc:
        logger.error("Ошибка генерации PDF для счёта №%s: %s", invoice.number, exc)
        return False

    tracking_url = _build_tracking_url(invoice)

    subject = f"Счёт №{invoice.number}"
    if invoice.period:
        subject += f" за {invoice.period.strftime('%m.%Y')}"

    html_body = render_to_string(
        "site/finances/invoice_email.html",
        {
            "invoice": invoice,
            "tracking_url": tracking_url,
        },
    )

    try:
        email = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        email.content_subtype = "html"
        email.attach(
            filename=f"invoice_{invoice.number}.pdf",
            content=pdf_bytes,
            mimetype="application/pdf",
        )
        email.send(fail_silently=False)
    except Exception as exc:
        logger.error(
            "Ошибка отправки email для счёта №%s на %s: %s",
            invoice.number, recipient_email, exc,
        )
        return False

    logger.info("Счёт №%s отправлен на %s", invoice.number, recipient_email)
    return True


def send_invoice_via_messenger(invoice, messenger: str, contact: str | None = None) -> bool:
    """
    Заглушка отправки счёта через мессенджер (Telegram / WhatsApp).
    TODO: интегрировать Telegram Bot API / WhatsApp Business API
    """
    logger.warning(
        "[STUB] Отправка счёта №%s через %s на %s не реализована.",
        invoice.number,
        messenger,
        contact or "неизвестный контакт",
    )
    return False


def _build_tracking_url(invoice) -> str:
    from django.urls import reverse
    try:
        path = reverse("finances:invoice_track_viewed", kwargs={"pk": invoice.pk})
        base = getattr(settings, "SITE_URL", "").rstrip("/")
        return f"{base}{path}"
    except Exception:
        return ""


def mark_invoice_viewed(invoice) -> bool:
    from finances.models import GeneratedInvoice

    if invoice.status == GeneratedInvoice.Status.SENT:
        invoice.status = GeneratedInvoice.Status.VIEWED
        invoice.save(update_fields=["status", "updated_at"])
        logger.info("Счёт №%s отмечен как просмотренный (tracking pixel)", invoice.number)
        return True
    return False


def send_invoice(invoice, sent_via: str, contact: str | None = None) -> bool:
    from finances.models import GeneratedInvoice

    success = False

    if sent_via == GeneratedInvoice.SentVia.EMAIL:
        success = send_invoice_via_email(invoice, recipient_email=contact)
    elif sent_via in (GeneratedInvoice.SentVia.TELEGRAM, GeneratedInvoice.SentVia.WHATSAPP):
        success = send_invoice_via_messenger(invoice, messenger=sent_via, contact=contact)
    elif sent_via == GeneratedInvoice.SentVia.MANUAL:
        success = True

    if success:
        invoice.status = GeneratedInvoice.Status.SENT
        invoice.sent_via = sent_via
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=["status", "sent_via", "sent_at", "updated_at"])

    return success