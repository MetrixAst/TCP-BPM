"""Применение глобальных финансовых фильтров из session к QuerySet."""

from datetime import date, timedelta

from django.db.models import Q

from finances.models import GeneratedInvoice


def get_filters(request):
    if request is None:
        return {}
    return dict(request.session.get('finance_filters') or {})


def parse_filter_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def has_active_filters(filters):
    return any(filters.get(k) for k in ('tenant', 'category', 'period_from', 'period_to'))


def _tenant_id(filters):
    raw = filters.get('tenant') or ''
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def apply_tenant(qs, filters, field='tenant'):
    tid = _tenant_id(filters)
    if tid:
        qs = qs.filter(**{f'{field}_id': tid})
    cat = filters.get('category') or ''
    if cat:
        try:
            qs = qs.filter(**{f'{field}__category_id': int(cat)})
        except (TypeError, ValueError):
            pass
    return qs


def apply_period(qs, filters, field):
    pf = parse_filter_date(filters.get('period_from'))
    pt = parse_filter_date(filters.get('period_to'))
    if pf:
        qs = qs.filter(**{f'{field}__gte': pf})
    if pt:
        qs = qs.filter(**{f'{field}__lte': pt})
    return qs


def filter_registry(qs, filters):
    return apply_period(apply_tenant(qs, filters), filters, 'period')


def filter_calendar(qs, filters):
    qs = apply_tenant(qs, filters)
    pf = parse_filter_date(filters.get('period_from'))
    pt = parse_filter_date(filters.get('period_to'))
    if not pf and not pt:
        return qs
    date_q = Q()
    if pf:
        date_q &= (
            Q(actual_date__gte=pf)
            | Q(actual_date__isnull=True, expected_date__gte=pf)
        )
    if pt:
        date_q &= (
            Q(actual_date__lte=pt)
            | Q(actual_date__isnull=True, expected_date__lte=pt)
        )
    return qs.filter(date_q)


def filter_cashflow(qs, filters):
    qs = apply_period(qs, filters, 'transaction_date')
    tid = _tenant_id(filters)
    if not tid:
        return qs

    invoice_pks = list(
        GeneratedInvoice.objects.filter(tenant_id=tid).values_list('pk', flat=True)
    )
    doc_nums = [f'INV-{pk}' for pk in invoice_pks]
    counterparty_ids = list(
        GeneratedInvoice.objects.filter(tenant_id=tid)
        .exclude(counterparty_id=None)
        .values_list('counterparty_id', flat=True)
        .distinct()
    )

    tenant_q = Q()
    if doc_nums:
        tenant_q |= Q(document_number__in=doc_nums)
    if counterparty_ids:
        tenant_q |= Q(counterparty_id__in=counterparty_ids)
    if not tenant_q:
        return qs.none()
    return qs.filter(tenant_q)


def cash_balance_date_bounds(filters, today=None):
    """Диапазон дат для остатка ДС (календарь факт)."""
    today = today or date.today()
    pf = parse_filter_date(filters.get('period_from'))
    pt = parse_filter_date(filters.get('period_to'))
    if pf or pt:
        return pf or (today - timedelta(days=90)), pt or today
    return today - timedelta(days=90), today
