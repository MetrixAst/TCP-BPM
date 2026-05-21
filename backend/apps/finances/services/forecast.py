from datetime import date, timedelta
from decimal import Decimal


def forecast_cashflow(horizon_days: int = 90) -> dict:
    """
    Прогноз денежного потока на horizon_days дней вперёд.

    Алгоритм:
    1. Берём PaymentCalendarEntry status=plan за ближайшие horizon_days дней.
    2. Считаем средний % исполнения из исторических fact
       (sum(actual_amount) / sum(expected_amount) за прошлые записи).
    3. Умножаем плановые поступления на коэффициент исполнения.
    4. Берём CashFlowRecord direction=outflow за последние 90 дней,
       вычисляем средний дневной расход и проецируем на горизонт.
    5. Определяем точки кассового разрыва (net_cf < 0 на дату).

    Возвращает: {labels, projected_income, projected_expense, net_cf, gap_dates}
    """
    from finances.models import PaymentCalendarEntry, CashFlowRecord
    from django.db.models import Sum

    today = date.today()
    end_date = today + timedelta(days=horizon_days)

    # ── 1. Плановые записи на горизонт ──────────────────────────────────────
    plan_entries = PaymentCalendarEntry.objects.filter(
        status=PaymentCalendarEntry.Status.PLAN,
        expected_date__gte=today,
        expected_date__lte=end_date,
    ).values('expected_date').annotate(total_expected=Sum('expected_amount'))

    plan_by_date = {row['expected_date']: float(row['total_expected'] or 0) for row in plan_entries}

    # ── 2. Коэффициент исполнения из исторических fact ───────────────────────
    historical_plan = PaymentCalendarEntry.objects.filter(
        status=PaymentCalendarEntry.Status.FACT,
        expected_date__lt=today,
    ).aggregate(
        total_expected=Sum('expected_amount'),
        total_actual=Sum('actual_amount'),
    )
    hist_expected = float(historical_plan['total_expected'] or 0)
    hist_actual   = float(historical_plan['total_actual'] or 0)
    execution_rate = (hist_actual / hist_expected) if hist_expected > 0 else 0.85

    # ── 3. Средний дневной расход (из последних 90 дней) ────────────────────
    lookback_start = today - timedelta(days=90)
    outflow_agg = CashFlowRecord.objects.filter(
        direction=CashFlowRecord.Direction.OUTFLOW,
        transaction_date__gte=lookback_start,
        transaction_date__lt=today,
    ).aggregate(total=Sum('amount'))
    total_outflow_90d = float(outflow_agg['total'] or 0)
    avg_daily_expense = total_outflow_90d / 90

    # ── 4. Строим прогноз по датам ───────────────────────────────────────────
    date_range = [today + timedelta(days=i) for i in range(horizon_days)]

    labels            = []
    projected_income  = []
    projected_expense = []
    net_cf            = []
    gap_dates         = []

    for d in date_range:
        raw_income = plan_by_date.get(d, 0)
        proj_income  = raw_income * execution_rate
        proj_expense = avg_daily_expense
        daily_net    = proj_income - proj_expense

        labels.append(d.isoformat())
        projected_income.append(round(proj_income, 2))
        projected_expense.append(round(proj_expense, 2))
        net_cf.append(round(daily_net, 2))

        if daily_net < 0:
            gap_dates.append(d.isoformat())

    return {
        'labels': labels,
        'projected_income': projected_income,
        'projected_expense': projected_expense,
        'net_cf': net_cf,
        'gap_dates': gap_dates,
    }
