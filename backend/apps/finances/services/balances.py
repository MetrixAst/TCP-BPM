from datetime import date
from decimal import Decimal


def get_balances_with_conversion(currency: str = 'USD') -> dict:
    """
    Возвращает ключевые балансы в KZT и указанной валюте.

    Данные:
    - cash_balance_kzt: сумма PaymentCalendarEntry(fact) за последние 90 дней
    - revenue_mtd_kzt: TenantPaymentRegistry.paid за текущий месяц
    """
    from datetime import timedelta
    from django.db.models import Sum
    from finances.models import ExchangeRate, PaymentCalendarEntry, TenantPaymentRegistry

    today = date.today()

    rate = ExchangeRate.objects.filter(
        currency=currency
    ).order_by('-date').first()

    ninety_days_ago = today - timedelta(days=90)
    cash_balance_kzt_agg = PaymentCalendarEntry.objects.filter(
        status=PaymentCalendarEntry.Status.FACT,
        actual_date__gte=ninety_days_ago,
        actual_date__lte=today,
    ).aggregate(total=Sum('actual_amount'))['total'] or Decimal('0')

    revenue_mtd_kzt_agg = TenantPaymentRegistry.objects.filter(
        period__year=today.year,
        period__month=today.month,
    ).aggregate(total=Sum('paid'))['total'] or Decimal('0')

    cash_balance_kzt = float(cash_balance_kzt_agg)
    revenue_mtd_kzt  = float(revenue_mtd_kzt_agg)

    if rate:
        try:
            cash_balance_foreign = float(
                ExchangeRate.convert(cash_balance_kzt, 'KZT', currency)
            )
        except (ValueError, Exception):
            cash_balance_foreign = None

        try:
            revenue_mtd_foreign = float(
                ExchangeRate.convert(revenue_mtd_kzt, 'KZT', currency)
            )
        except (ValueError, Exception):
            revenue_mtd_foreign = None
    else:
        cash_balance_foreign = None
        revenue_mtd_foreign  = None

    rate_is_fresh = (today - rate.date).days <= 1 if rate else False

    return {
        'cash_balance_kzt': cash_balance_kzt,
        'cash_balance_foreign': cash_balance_foreign,
        'revenue_mtd_kzt': revenue_mtd_kzt,
        'revenue_mtd_foreign': revenue_mtd_foreign,
        'currency': currency,
        'rate': float(rate.rate) if rate else None,
        'rate_date': str(rate.date) if rate else None,
        'rate_is_fresh': rate_is_fresh,
    }
