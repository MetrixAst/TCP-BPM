"""Разбор полей ответов 1С (разные имена ключей)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _first(data: dict, *keys, default=None):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def parse_decimal(value) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value).replace(' ', '').replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def period_from_date(d: date | None) -> date | None:
    if not d:
        return None
    return d.replace(day=1)


def payment_direction(payment_type: str) -> str:
    """CashFlowRecord.Direction value."""
    from finances.models import CashFlowRecord

    t = (payment_type or '').lower()
    if any(x in t for x in ('in', 'приход', 'поступ', 'income', 'receipt')):
        return CashFlowRecord.Direction.INFLOW
    return CashFlowRecord.Direction.OUTFLOW


def map_invoice_status(status: str) -> str:
    from finances.models import GeneratedInvoice

    s = (status or '').lower()
    mapping = {
        'paid': GeneratedInvoice.Status.PAID,
        'оплачен': GeneratedInvoice.Status.PAID,
        'sent': GeneratedInvoice.Status.SENT,
        'отправлен': GeneratedInvoice.Status.SENT,
        'viewed': GeneratedInvoice.Status.VIEWED,
        'просмотрен': GeneratedInvoice.Status.VIEWED,
        'created': GeneratedInvoice.Status.CREATED,
        'draft': GeneratedInvoice.Status.CREATED,
        'cancelled': GeneratedInvoice.Status.CANCELLED,
    }
    return mapping.get(s, GeneratedInvoice.Status.SENT)


def registry_status(charged: Decimal, paid: Decimal, planned: date | None) -> str:
    from finances.models import TenantPaymentRegistry

    balance = charged - paid
    if balance <= 0 and charged > 0:
        return TenantPaymentRegistry.Status.PAID
    if paid > 0:
        return TenantPaymentRegistry.Status.PARTIAL
    if planned and planned < date.today():
        return TenantPaymentRegistry.Status.OVERDUE
    return TenantPaymentRegistry.Status.PENDING


def document_registry_fields(doc: dict) -> dict:
    """Унифицированные поля строки реестра из документа 1С (balance.by_documents)."""
    charged = parse_decimal(_first(
        doc, 'charged', 'Charged', 'amount', 'Amount', 'sum', 'начислено',
    ))
    paid = parse_decimal(_first(
        doc, 'paid', 'Paid', 'paid_amount', 'paidAmount', 'оплачено',
    ))
    debt = parse_decimal(_first(doc, 'debt', 'Debt', 'balance', 'Balance', 'остаток'))
    if charged == 0 and debt != 0:
        charged = abs(debt) + paid
    if paid == 0 and charged > 0 and debt != 0:
        paid = max(charged - abs(debt), Decimal('0'))

    doc_date = parse_date(_first(
        doc, 'date', 'Date', 'period', 'Period', 'document_date', 'due_date',
    ))
    return {
        'onec_id': str(_first(doc, 'id', 'Id', 'document_id', 'onec_id', default=''))[:100],
        'contract_number': str(_first(
            doc, 'contract_number', 'contractNumber', 'contract', 'number', 'Number',
            default='—',
        ))[:100],
        'period': period_from_date(doc_date) or date.today().replace(day=1),
        'planned_date': parse_date(_first(doc, 'planned_date', 'due_date', 'dueDate', 'date')),
        'actual_date': parse_date(_first(doc, 'actual_date', 'payment_date', 'paid_date')),
        'charged': charged,
        'paid': paid,
        'balance': max(charged - paid, Decimal('0')),
    }
