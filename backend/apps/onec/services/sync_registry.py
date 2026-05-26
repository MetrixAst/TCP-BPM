"""Импорт реестра аренды и факта календаря из 1С (balance + invoices)."""

from __future__ import annotations

import logging
from datetime import date

from django.utils import timezone

from finances.models import PaymentCalendarEntry, TenantPaymentRegistry
from onec.models import Counterparty

from .client_factory import get_onec_client, is_onec_configured
from .parsers import map_invoice_status, parse_date, parse_decimal, period_from_date, registry_status
from .parsers import document_registry_fields
from .tenant_resolver import resolve_tenant_for_counterparty

logger = logging.getLogger(__name__)


def _upsert_registry_row(
    *,
    tenant,
    onec_id: str,
    contract_number: str,
    period: date,
    charged,
    paid,
    planned_date=None,
    actual_date=None,
) -> None:
    if not tenant or not onec_id:
        return

    balance = max(charged - paid, parse_decimal(0))
    status = registry_status(charged, paid, planned_date)

    entry, _ = TenantPaymentRegistry.objects.update_or_create(
        onec_id=onec_id[:100],
        defaults={
            'tenant': tenant,
            'contract_number': contract_number[:100],
            'period': period,
            'charged': charged,
            'paid': paid,
            'balance': balance,
            'planned_date': planned_date,
            'actual_date': actual_date,
            'status': status,
            'overdue_days': max((date.today() - planned_date).days, 0) if (
                planned_date and status == TenantPaymentRegistry.Status.OVERDUE
            ) else 0,
            'synced_at': timezone.now(),
        },
    )
    entry.save()


def _sync_balance_documents(client, counterparty: Counterparty, tenant) -> int:
    count = 0
    try:
        balance = client.get_balance(counterparty_id=counterparty.id_1c)
    except Exception as exc:
        logger.warning('balance %s: %s', counterparty.id_1c, exc)
        return 0

    docs = balance.by_documents or balance.documents or []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        fields = document_registry_fields(doc)
        oid = fields['onec_id'] or f'bal-{counterparty.id_1c}-{fields["contract_number"]}-{fields["period"]}'
        _upsert_registry_row(
            tenant=tenant,
            onec_id=oid,
            contract_number=fields['contract_number'],
            period=fields['period'],
            charged=fields['charged'],
            paid=fields['paid'],
            planned_date=fields['planned_date'],
            actual_date=fields['actual_date'],
        )
        count += 1
    return count


def _sync_invoices_as_registry(client, counterparty: Counterparty, tenant) -> int:
    from datetime import timedelta
    from django.conf import settings

    days = int(getattr(settings, 'ONE_C_SYNC_SINCE_DAYS', 365))
    since = date.today() - timedelta(days=days)
    count = 0
    try:
        invoices = client.get_invoices(since=since, limit=500)
    except Exception as exc:
        logger.warning('invoices for %s: %s', counterparty.id_1c, exc)
        return 0

    for inv in invoices:
        if inv.counterparty_id and inv.counterparty_id != counterparty.id_1c:
            continue
        period = period_from_date(parse_date(inv.date)) or date.today().replace(day=1)
        amount = parse_decimal(inv.amount)
        paid = parse_decimal(inv.paid_amount) if inv.paid_amount is not None else (
            amount if (inv.status or '').lower() == 'paid' else parse_decimal(0)
        )
        _upsert_registry_row(
            tenant=tenant,
            onec_id=f'inv-{inv.id}'[:100],
            contract_number=inv.number or f'Счёт-{inv.id}',
            period=period,
            charged=amount,
            paid=paid,
            planned_date=parse_date(inv.date),
            actual_date=parse_date(inv.date) if paid >= amount else None,
        )
        if paid > 0:
            PaymentCalendarEntry.objects.update_or_create(
                onec_id=f'cal-{inv.id}'[:100],
                defaults={
                    'tenant': tenant,
                    'contract_number': (inv.number or '')[:100],
                    'expected_date': parse_date(inv.date) or period,
                    'expected_amount': amount,
                    'actual_amount': paid,
                    'actual_date': parse_date(inv.date),
                    'status': PaymentCalendarEntry.Status.FACT,
                    'synced_at': timezone.now(),
                },
            )
        count += 1
    return count


def sync_registry_from_1c() -> dict:
    if not is_onec_configured():
        return {'status': 'skipped', 'reason': 'onec_not_configured'}

    client = get_onec_client()
    rows = 0
    skipped_cp = 0

    for counterparty in Counterparty.objects.iterator():
        tenant = resolve_tenant_for_counterparty(counterparty)
        if not tenant:
            skipped_cp += 1
            continue
        rows += _sync_balance_documents(client, counterparty, tenant)
        rows += _sync_invoices_as_registry(client, counterparty, tenant)

    return {
        'status': 'ok',
        'rows': rows,
        'counterparties_without_tenant': skipped_cp,
    }
