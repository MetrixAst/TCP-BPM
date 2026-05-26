"""Импорт платежей 1С → finances.CashFlowRecord (ДДС)."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from finances.models import CashFlowRecord
from onec.client_1c.models import Payment as OneCPayment
from onec.models import Counterparty

from .client_factory import get_onec_client, is_onec_configured
from .parsers import parse_date, parse_decimal, payment_direction

logger = logging.getLogger(__name__)


def _since_date() -> date:
    days = int(getattr(settings, 'ONE_C_SYNC_SINCE_DAYS', 90))
    return date.today() - timedelta(days=days)


def upsert_payment(payment: OneCPayment | dict, *, onec_id: str | None = None) -> str:
    if isinstance(payment, dict):
        pid = onec_id or str(payment.get('id', ''))
        ptype = payment.get('type', '')
        amount = parse_decimal(payment.get('amount'))
        currency = payment.get('currency', 'KZT') or 'KZT'
        tx_date = parse_date(payment.get('date')) or date.today()
        purpose = payment.get('purpose', '') or payment.get('description', '')
        number = payment.get('number', '')
        cp_id_1c = payment.get('counterparty_id', '')
    else:
        pid = onec_id or payment.id
        ptype = payment.type
        amount = parse_decimal(payment.amount)
        currency = payment.currency or 'KZT'
        tx_date = parse_date(payment.date) or date.today()
        purpose = payment.purpose or ''
        number = payment.number
        cp_id_1c = payment.counterparty_id

    if not pid:
        return 'skipped'

    counterparty = None
    if cp_id_1c:
        counterparty = Counterparty.objects.filter(id_1c=cp_id_1c).first()

    direction = payment_direction(ptype)
    defaults = {
        'direction': direction,
        'flow_type': CashFlowRecord.FlowType.OPERATING,
        'amount': amount,
        'currency': currency[:3] if currency else 'KZT',
        'transaction_date': tx_date,
        'value_date': tx_date,
        'description': purpose or f'Платёж 1С №{number}',
        'document_number': number or None,
        'counterparty': counterparty,
        'synced_at': timezone.now(),
    }

    CashFlowRecord.objects.update_or_create(
        onec_id=str(pid)[:100],
        defaults=defaults,
    )
    return 'updated'


def sync_cashflow_from_1c() -> dict:
    if not is_onec_configured():
        return {'status': 'skipped', 'reason': 'onec_not_configured'}

    client = get_onec_client()
    since = _since_date()
    created = updated = skipped = 0

    try:
        payments = client.get_payments(since=since)
    except Exception as exc:
        logger.exception('sync_cashflow get_payments failed: %s', exc)
        return {'status': 'error', 'error': str(exc)}

    for payment in payments:
        try:
            before = CashFlowRecord.objects.filter(onec_id=payment.id).exists()
            upsert_payment(payment)
            if before:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            logger.warning('sync_cashflow payment %s: %s', payment.id, exc)
            skipped += 1

    return {
        'status': 'ok',
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'total': len(payments),
    }
