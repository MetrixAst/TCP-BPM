"""
Связь выставленных счетов с реестром платежей и календарём.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from finances.models import (
    CashFlowRecord,
    GeneratedInvoice,
    PaymentCalendarEntry,
    TenantPaymentRegistry,
)


def _registry_period(invoice: GeneratedInvoice) -> date:
    """Период реестра — первое число месяца счёта."""
    if invoice.period:
        return invoice.period.replace(day=1)
    ref = invoice.created_at.date() if invoice.created_at else date.today()
    return ref.replace(day=1)


def _registry_contract(invoice: GeneratedInvoice) -> str:
    contract = (invoice.contract_number or '').strip()
    if contract:
        return contract[:100]
    return f'Счёт-{invoice.number}'[:100]


def _registry_status(charged: Decimal, paid: Decimal) -> str:
    balance = charged - paid
    if balance <= 0:
        return TenantPaymentRegistry.Status.PAID
    if paid > 0:
        return TenantPaymentRegistry.Status.PARTIAL
    return TenantPaymentRegistry.Status.PENDING


def _sync_payment_calendar(
    invoice: GeneratedInvoice,
    *,
    contract: str,
    amount: Decimal,
    pay_date: date,
) -> PaymentCalendarEntry:
    cal, _created = PaymentCalendarEntry.objects.get_or_create(
        tenant_id=invoice.tenant_id,
        contract_number=contract,
        expected_date=pay_date,
        defaults={
            'expected_amount': amount,
            'actual_amount': Decimal('0'),
            'status': PaymentCalendarEntry.Status.PLAN,
        },
    )
    cal.expected_amount = max(cal.expected_amount or Decimal('0'), amount)
    cal.actual_amount = (cal.actual_amount or Decimal('0')) + amount
    cal.actual_date = pay_date
    cal.status = PaymentCalendarEntry.Status.FACT
    cal.save()
    return cal


def _sync_cashflow_inflow(
    invoice: GeneratedInvoice,
    *,
    amount: Decimal,
    pay_date: date,
) -> CashFlowRecord:
    doc_key = f'INV-{invoice.pk}'
    description = f'Оплата счёта №{invoice.number}'
    defaults = {
        'direction': CashFlowRecord.Direction.INFLOW,
        'flow_type': CashFlowRecord.FlowType.OPERATING,
        'amount': amount,
        'currency': 'KZT',
        'transaction_date': pay_date,
        'value_date': pay_date,
        'description': description,
        'document_number': doc_key,
        'counterparty_id': invoice.counterparty_id,
    }
    record, created = CashFlowRecord.objects.get_or_create(
        document_number=doc_key,
        defaults=defaults,
    )
    if not created:
        record.amount = amount
        record.transaction_date = pay_date
        record.description = description
        record.counterparty_id = invoice.counterparty_id
        record.save()
    return record


def apply_invoice_payment_to_registry(invoice: GeneratedInvoice) -> TenantPaymentRegistry | None:
    """
    При оплате счёта обновляет реестр, календарь платежей и поступление в ДДС.

    Возвращает запись реестра или None, если у счёта не указан арендатор.
    """
    if not invoice.tenant_id:
        return None

    doc_key = f'INV-{invoice.pk}'
    if CashFlowRecord.objects.filter(document_number=doc_key).exists():
        return TenantPaymentRegistry.objects.filter(
            tenant_id=invoice.tenant_id,
            contract_number=_registry_contract(invoice),
            period=_registry_period(invoice),
        ).first()

    amount = Decimal(invoice.total_amount or 0)
    period = _registry_period(invoice)
    contract = _registry_contract(invoice)
    today = date.today()

    entry, _created = TenantPaymentRegistry.objects.get_or_create(
        tenant_id=invoice.tenant_id,
        contract_number=contract,
        period=period,
        defaults={
            'charged': amount,
            'paid': Decimal('0'),
            'balance': amount,
            'status': TenantPaymentRegistry.Status.PENDING,
            'planned_date': period,
        },
    )

    charged = entry.charged or Decimal('0')
    if charged < amount:
        charged = amount

    paid_before = entry.paid or Decimal('0')
    remaining = max(charged - paid_before, Decimal('0'))
    apply_amount = min(amount, remaining)

    new_paid = paid_before + apply_amount
    entry.charged = charged
    entry.paid = new_paid
    entry.balance = max(charged - new_paid, Decimal('0'))
    entry.status = _registry_status(charged, new_paid)
    entry.actual_date = today
    if entry.status == TenantPaymentRegistry.Status.PAID:
        entry.overdue_days = 0
    entry.save()

    if apply_amount > 0:
        _sync_payment_calendar(
            invoice, contract=contract, amount=apply_amount, pay_date=today,
        )
    _sync_cashflow_inflow(invoice, amount=amount, pay_date=today)

    return entry
