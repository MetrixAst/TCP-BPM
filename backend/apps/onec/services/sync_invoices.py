"""Синхронизация статусов счетов BPM ↔ 1С."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from finances.models import GeneratedInvoice
from onec.models import Counterparty

from .client_factory import get_onec_client, is_onec_configured
from .parsers import map_invoice_status, parse_date

logger = logging.getLogger(__name__)


def _match_invoice(onec_inv) -> GeneratedInvoice | None:
    qs = GeneratedInvoice.objects.all()
    if onec_inv.id:
        found = qs.filter(onec_id=onec_inv.id).first()
        if found:
            return found
    if onec_inv.number:
        found = qs.filter(number=onec_inv.number).order_by('-created_at').first()
        if found:
            return found
    if onec_inv.counterparty_id:
        cp = Counterparty.objects.filter(id_1c=onec_inv.counterparty_id).first()
        if cp:
            found = qs.filter(counterparty=cp, total_amount=onec_inv.amount).order_by('-created_at').first()
            if found:
                return found
    return None


def sync_generated_invoices_from_1c() -> dict:
    """Подтянуть статусы и номера 1С для finances.GeneratedInvoice."""
    if not is_onec_configured():
        return {'status': 'skipped', 'reason': 'onec_not_configured'}

    client = get_onec_client()
    days = int(getattr(settings, 'ONE_C_SYNC_SINCE_DAYS', 365))
    since = date.today() - timedelta(days=days)

    matched = updated = skipped = 0
    try:
        invoices = client.get_invoices(since=since, limit=1000)
    except Exception as exc:
        logger.exception('sync_invoices: %s', exc)
        return {'status': 'error', 'error': str(exc)}

    for onec_inv in invoices:
        local = _match_invoice(onec_inv)
        if not local:
            skipped += 1
            continue
        matched += 1
        new_status = map_invoice_status(onec_inv.status)
        fields = ['onec_id', 'onec_invoice_number', 'onec_status', 'synced_at']
        local.onec_id = onec_inv.id or local.onec_id
        local.onec_invoice_number = onec_inv.number or local.onec_invoice_number
        local.onec_status = onec_inv.status or local.onec_status
        local.synced_at = timezone.now()
        if new_status == GeneratedInvoice.Status.PAID:
            local.status = GeneratedInvoice.Status.PAID
        elif local.status == GeneratedInvoice.Status.CREATED and new_status != GeneratedInvoice.Status.CREATED:
            local.status = new_status
        local.save(update_fields=['status'] + fields)
        updated += 1

    return {
        'status': 'ok',
        'matched': matched,
        'updated': updated,
        'skipped': skipped,
        'total_from_1c': len(invoices),
    }


def notify_onec_invoice_sent(invoice: GeneratedInvoice) -> bool:
    """
    Подтверждение в 1С (очередь /confirm), что BPM принял/отправил счёт.
    После настройки URL полный статус подтянется через sync_generated_invoices_from_1c.
    """
    if not is_onec_configured():
        return False
    try:
        client = get_onec_client()
        client.get_data(limit=10)
        client.confirm(
            received_ids=[f'bpm-invoice-{invoice.pk}'],
            status='sent',
            sync_token=f'bpm_invoice_{invoice.pk}',
        )
        invoice.onec_status = 'sent'
        invoice.synced_at = timezone.now()
        invoice.save(update_fields=['onec_status', 'synced_at'])
        return True
    except Exception as exc:
        logger.warning('notify_onec_invoice_sent %s: %s', invoice.pk, exc)
        return False
