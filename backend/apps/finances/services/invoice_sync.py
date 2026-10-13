"""
Загрузка счетов и оплат из invoice-сервиса в финансовый блок BPM.

Счета выставляются бухгалтерией в 1С. Invoice-сервис забирает их вместе с
оплатами, а BPM раскладывает по своим разделам:

- «Счета» (GeneratedInvoice) — номер, позиции, сумма, срок, оплата;
- «Реестр платежей арендаторов» — начислено / оплачено / долг / просрочка;
- «Календарь платежей» — план (срок оплаты) и факт (дата поступления).

Реестр и календарь привязаны к арендатору BPM. Счёт, контрагента которого не
удалось сопоставить с арендатором, сохраняется только в «Счетах» и попадает в
список несопоставленных — его видно на экране синхронизации.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from finances.models import GeneratedInvoice, GeneratedInvoiceItem, InvoiceSyncRun, PaymentCalendarEntry, TenantPaymentRegistry
from .invoice_service import InvoiceServiceClient, configured_tenant_ids
from .rent_plan import drop_plan_for_invoice

logger = logging.getLogger(__name__)

LEGAL_FORMS = re.compile(r'\b(тоо|ип|ао|оао|зао|ооо|llp|ltd)\b', re.IGNORECASE)


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    return parse_date(text[:10])


def _datetime(value) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def normalize_name(name: str) -> str:
    text = LEGAL_FORMS.sub(' ', (name or '').lower())
    text = re.sub(r'[«»"\'`.,()]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def recent_periods(months: int, today: date | None = None) -> list[str]:
    today = today or timezone.localdate()
    result = []
    year, month = today.year, today.month
    for _ in range(months):
        result.append(f'{year:04d}-{month:02d}')
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return result


class TenantMatcher:
    """Сопоставляет контрагента 1С с арендатором BPM: по ID 1С, затем по названию."""

    def __init__(self):
        from onec.models import Counterparty
        from tenants.models import Tenant

        self._by_onec_id = {}
        for cp in Counterparty.objects.exclude(id_1c=''):
            self._by_onec_id[cp.id_1c] = cp
        self._tenants_by_name = {}
        for tenant in Tenant.objects.all():
            self._tenants_by_name.setdefault(normalize_name(tenant.name), tenant)

    def counterparty(self, onec_id: str, name: str, bin_value: str):
        from onec.models import Counterparty

        cp = self._by_onec_id.get(onec_id) if onec_id else None
        if cp is None and bin_value:
            cp = Counterparty.objects.filter(bin_number=bin_value).first()
        if cp is None and onec_id:
            cp = Counterparty.objects.create(
                id_1c=onec_id,
                full_name=name or onec_id,
                short_name=(name or onec_id)[:255],
                bin_number=bin_value or None,
                is_customer=True,
                synced_at=timezone.now(),
            )
        if cp is not None and onec_id:
            self._by_onec_id[onec_id] = cp
        return cp

    def tenant(self, counterparty, name: str):
        from onec.services.tenant_resolver import resolve_tenant_for_counterparty

        tenant = resolve_tenant_for_counterparty(counterparty) if counterparty else None
        return tenant or self._tenants_by_name.get(normalize_name(name))


def _registry_status(service_status: str, due: date | None, today: date) -> str:
    S = TenantPaymentRegistry.Status
    if service_status == 'paid':
        return S.PAID
    if service_status == 'partial':
        return S.OVERDUE if due and due < today else S.PARTIAL
    if service_status in ('overdue', 'needs_review'):
        return S.OVERDUE
    return S.OVERDUE if due and due < today else S.PENDING


def _calendar_status(service_status: str, due: date | None, today: date) -> str:
    S = PaymentCalendarEntry.Status
    if service_status == 'paid':
        return S.FACT
    if service_status == 'overdue' or (due and due < today):
        return S.OVERDUE
    return S.PLAN


class InvoiceSync:
    def __init__(self, client: InvoiceServiceClient | None = None):
        self.client = client or InvoiceServiceClient()
        self.matcher = TenantMatcher()
        self.today = timezone.localdate()
        self.stats = {'invoices': 0, 'items': 0, 'registry': 0, 'calendar': 0, 'unmatched': 0}
        self.unmatched = {}

    def run_period(self, period: str, tenant_id=None):
        invoices = self.client.list_invoices(period, tenant_id=tenant_id)
        payments = {
            str(p.get('invoice_id')): p
            for p in self.client.list_payments(period, tenant_id=tenant_id)
            if p.get('invoice_id')
        }
        for row in invoices:
            if (row.get('status') or '').lower() == 'draft':
                continue
            self._apply(row, payments.get(str(row.get('id'))), period, tenant_id)

    @transaction.atomic
    def _apply(self, row: dict, payment: dict | None, period: str, service_tenant_id):
        invoice_guid = str(row.get('id') or '')
        if not invoice_guid:
            return
        cp_data = row.get('counterparty') or {}
        cp_id = str(row.get('counterparty_id') or cp_data.get('id') or '')
        cp_name = row.get('counterparty_name') or cp_data.get('name') or ''
        cp_bin = (cp_data.get('bin') or '').strip()

        counterparty = self.matcher.counterparty(cp_id, cp_name, cp_bin)
        tenant = self.matcher.tenant(counterparty, cp_name)

        payment = payment or {}
        amount = _decimal(row.get('amount') or payment.get('amount'))
        paid_amount = _decimal(payment.get('paid_amount'))
        due = _date(payment.get('due_date')) or _date(row.get('date'))
        paid_at = _datetime(payment.get('paid_at'))
        service_status = (payment.get('status') or 'unpaid').lower()
        period_date = date(int(period[:4]), int(period[5:7]), 1)
        number = str(row.get('number') or invoice_guid[:8])

        invoice = GeneratedInvoice.objects.filter(onec_id=invoice_guid).first() or GeneratedInvoice(
            onec_id=invoice_guid, status=GeneratedInvoice.Status.CREATED,
        )
        invoice.tenant = tenant
        invoice.counterparty = counterparty
        invoice.counterparty_onec_id = cp_id or None
        invoice.counterparty_name = cp_name[:255] or None
        invoice.number = number
        invoice.onec_invoice_number = number
        invoice.period = period_date
        invoice.total_amount = amount
        invoice.vat_amount = _decimal(row.get('vat'))
        invoice.due_date = due
        invoice.paid_amount = paid_amount
        invoice.paid_at = paid_at
        invoice.service_type = payment.get('service_type') or invoice.service_type
        invoice.service_payment_id = payment.get('id') or invoice.service_payment_id
        invoice.service_tenant_id = service_tenant_id
        invoice.onec_status = row.get('status') or ''
        invoice.synced_at = timezone.now()
        if service_status == 'paid':
            invoice.status = GeneratedInvoice.Status.PAID
        elif invoice.status == GeneratedInvoice.Status.PAID:
            invoice.status = GeneratedInvoice.Status.SENT
        if payment.get('notifications') and invoice.status == GeneratedInvoice.Status.CREATED:
            invoice.status = GeneratedInvoice.Status.SENT
        invoice.save()
        self.stats['invoices'] += 1

        items = row.get('items') or []
        if items:
            invoice.items.all().delete()
            for item in items:
                line = GeneratedInvoiceItem(
                    invoice=invoice,
                    name=(item.get('name') or '—')[:255],
                    quantity=_decimal(item.get('quantity') or 1),
                    price=_decimal(item.get('price')),
                    vat_rate=Decimal('0'),
                )
                line.save()
                self.stats['items'] += 1

        if tenant is None:
            self.stats['unmatched'] += 1
            key = cp_id or cp_name
            entry = self.unmatched.setdefault(key, {'name': cp_name, 'onec_id': cp_id, 'bin': cp_bin, 'invoices': 0})
            entry['invoices'] += 1
            return

        balance = max(amount - paid_amount, Decimal('0.00'))
        overdue_days = (self.today - due).days if due and balance > 0 and due < self.today else 0

        TenantPaymentRegistry.objects.update_or_create(
            onec_id=f'inv:{invoice_guid}',
            defaults={
                'tenant': tenant,
                'contract_number': f'Счёт {number}',
                'period': period_date,
                'charged': amount,
                'paid': paid_amount,
                'balance': balance,
                'planned_date': due,
                'actual_date': paid_at.date() if paid_at else None,
                'overdue_days': overdue_days,
                'status': _registry_status(service_status, due, self.today),
                'synced_at': timezone.now(),
            },
        )
        self.stats['registry'] += 1

        if due:
            PaymentCalendarEntry.objects.update_or_create(
                onec_id=f'inv:{invoice_guid}',
                defaults={
                    'tenant': tenant,
                    'contract_number': f'Счёт {number}',
                    'expected_date': due,
                    'expected_amount': amount,
                    'actual_amount': paid_amount,
                    'actual_date': paid_at.date() if paid_at else None,
                    'status': _calendar_status(service_status, due, self.today),
                    'synced_at': timezone.now(),
                },
            )
            self.stats['calendar'] += 1
            drop_plan_for_invoice(tenant.pk, period_date)


def sync_invoices_from_service(*, months: int | None = None, trigger: str = 'schedule',
                               client: InvoiceServiceClient | None = None) -> InvoiceSyncRun:
    from django.conf import settings

    months = months or getattr(settings, 'INVOICE_SERVICE_SYNC_MONTHS', 3)
    periods = recent_periods(months)
    run = InvoiceSyncRun.objects.create(trigger=trigger, periods=', '.join(periods))
    errors = []
    try:
        sync = InvoiceSync(client)
        for tenant_id in configured_tenant_ids():
            for period in periods:
                try:
                    sync.run_period(period, tenant_id=tenant_id)
                except Exception as exc:  # одна организация/период не должна ронять остальные
                    logger.exception('Invoice sync failed: period=%s tenant=%s', period, tenant_id)
                    errors.append(f'{period}: {exc}')
        run.stats = sync.stats
        run.unmatched = sorted(sync.unmatched.values(), key=lambda x: -x['invoices'])
        if errors:
            run.status = InvoiceSyncRun.Status.FAILED if not sync.stats['invoices'] else InvoiceSyncRun.Status.PARTIAL
            run.error = '\n'.join(errors)[:5000]
        else:
            run.status = InvoiceSyncRun.Status.PARTIAL if sync.unmatched else InvoiceSyncRun.Status.OK
    except Exception as exc:
        logger.exception('Invoice sync failed')
        run.status = InvoiceSyncRun.Status.FAILED
        run.error = str(exc)[:5000]
    run.finished_at = timezone.now()
    run.save()
    return run
