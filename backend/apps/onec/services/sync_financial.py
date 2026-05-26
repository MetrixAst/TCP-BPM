"""ОПиУ и факт бюджета из записей 1С (/data и типизированные payload)."""

from __future__ import annotations

import logging

from django.utils import timezone

from finances.models import BudgetCategory, BudgetItem, FinancialStatement

from .parsers import parse_date, parse_decimal, period_from_date, _first

logger = logging.getLogger(__name__)


def _apply_opiu_payload(data: dict, *, onec_id: str | None = None) -> bool:
    period_type = _first(data, 'period_type', 'periodType', default='monthly')
    year = int(_first(data, 'year', 'Year', default=0) or 0)
    month = _first(data, 'month', 'Month')
    quarter = _first(data, 'quarter', 'Quarter')

    if not year:
        d = parse_date(_first(data, 'period', 'date', 'Date'))
        if d:
            year, month = d.year, d.month
        else:
            return False

    defaults = {
        'revenue_plan': parse_decimal(_first(data, 'revenue_plan', 'revenuePlan')),
        'revenue_fact': parse_decimal(_first(data, 'revenue_fact', 'revenueFact', 'revenue')),
        'revenue_forecast': parse_decimal(_first(data, 'revenue_forecast', 'revenueForecast')),
        'ebitda_plan': parse_decimal(_first(data, 'ebitda_plan', 'ebitdaPlan')),
        'ebitda_fact': parse_decimal(_first(data, 'ebitda_fact', 'ebitdaFact', 'ebitda')),
        'ebitda_forecast': parse_decimal(_first(data, 'ebitda_forecast', 'ebitdaForecast')),
        'operating_profit_plan': parse_decimal(_first(data, 'operating_profit_plan', 'operatingProfitPlan')),
        'operating_profit_fact': parse_decimal(_first(data, 'operating_profit_fact', 'operatingProfitFact')),
        'net_profit_plan': parse_decimal(_first(data, 'net_profit_plan', 'netProfitPlan')),
        'net_profit_fact': parse_decimal(_first(data, 'net_profit_fact', 'netProfitFact', 'net_profit', 'netProfit')),
        'net_profit_forecast': parse_decimal(_first(data, 'net_profit_forecast', 'netProfitForecast')),
    }

    lookup = {'period_type': period_type, 'year': year, 'month': month, 'quarter': quarter}
    defaults['onec_synced_at'] = timezone.now()
    if onec_id:
        FinancialStatement.objects.update_or_create(
            onec_id=str(onec_id)[:100],
            defaults={**defaults, **lookup},
        )
    else:
        FinancialStatement.objects.update_or_create(
            **lookup,
            defaults=defaults,
        )
    return True


def _apply_budget_fact_payload(data: dict) -> bool:
    code = _first(data, 'category_code', 'categoryCode', 'code')
    if not code:
        return False
    category = BudgetCategory.objects.filter(code=code).first()
    if not category:
        return False

    year = int(_first(data, 'year', default=0) or 0)
    month = _first(data, 'month')
    fact = parse_decimal(_first(data, 'fact', 'Fact', 'amount'))
    if not year:
        return False

    BudgetItem.objects.update_or_create(
        category=category,
        period_type=BudgetItem.Period.MONTHLY,
        year=year,
        month=month,
        quarter=None,
        defaults={'fact': fact},
    )
    return True


def process_data_record(record_type: str, payload: dict, *, record_id: str) -> str:
    """Маршрутизация записи очереди /data."""
    t = (record_type or '').lower()
    if t in ('financial_statement', 'opiu', 'pnl', 'profit_loss', 'statement'):
        if _apply_opiu_payload(payload, onec_id=record_id):
            return 'opiu'
    if t in ('budget_fact', 'budget', 'budget_item'):
        if _apply_budget_fact_payload(payload):
            return 'budget'
    if t in ('payment', 'cashflow', 'dds'):
        from .sync_cashflow import upsert_payment
        upsert_payment(payload, onec_id=record_id)
        return 'payment'
    if t in ('invoice', 'registry', 'rent'):
        return 'routed'
    return 'ignored'


def sync_financial_from_1c() -> dict:
    from .sync_data_queue import sync_data_queue_from_1c

    return sync_data_queue_from_1c(financial_only=True)
