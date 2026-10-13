from datetime import date, timedelta

# ТЗ 4.11: Base / Stress / Optimistic — множители поступлений и расходов.
SCENARIOS = {
    'base':       {'label': 'Базовый',        'income': 1.0, 'expense': 1.0},
    'stress':     {'label': 'Стресс',         'income': 0.8, 'expense': 1.1},
    'optimistic': {'label': 'Оптимистичный',  'income': 1.1, 'expense': 0.95},
}


def opening_balance() -> float:
    """Остаток ДС на сегодня по выписке ДДС (поступления − выбытия)."""
    from django.db.models import Sum
    from finances.models import CashFlowRecord

    today = date.today()
    totals = {
        row['direction']: float(row['total'] or 0)
        for row in CashFlowRecord.objects.filter(transaction_date__lte=today)
        .values('direction').annotate(total=Sum('amount'))
    }
    return totals.get(CashFlowRecord.Direction.INFLOW, 0.0) - totals.get(CashFlowRecord.Direction.OUTFLOW, 0.0)


def forecast_cashflow(horizon_days: int = 90, *, group: str = 'day', scenario: str = 'base',
                      start_balance: float | None = None) -> dict:
    """
    Прогноз денежного потока на horizon_days дней вперёд.

    1. Поступления — плановые записи календаря (счета из 1С и план по договорам),
       умноженные на исторический процент собираемости.
    2. Расходы — средний дневной расход по выписке ДДС за 90 дней.
    3. Остаток — накопительно от текущего остатка по ДДС; кассовый разрыв —
       дата, когда прогнозный остаток уходит в минус.
    4. group='week' — агрегирование по неделям (режим «12 недель» для CFO).
    """
    from django.db.models import Sum
    from finances.models import CashFlowRecord, PaymentCalendarEntry

    factors = SCENARIOS.get(scenario, SCENARIOS['base'])
    today = date.today()
    end_date = today + timedelta(days=horizon_days)

    plan_by_date = {
        row['expected_date']: float(row['total_expected'] or 0)
        for row in PaymentCalendarEntry.objects.filter(
            status=PaymentCalendarEntry.Status.PLAN,
            expected_date__gte=today,
            expected_date__lt=end_date,
        ).values('expected_date').annotate(total_expected=Sum('expected_amount'))
    }

    historical = PaymentCalendarEntry.objects.filter(
        status=PaymentCalendarEntry.Status.FACT,
        expected_date__lt=today,
    ).aggregate(total_expected=Sum('expected_amount'), total_actual=Sum('actual_amount'))
    hist_expected = float(historical['total_expected'] or 0)
    hist_actual = float(historical['total_actual'] or 0)
    execution_rate = min(hist_actual / hist_expected, 1.0) if hist_expected > 0 else 0.85

    total_outflow_90d = float(CashFlowRecord.objects.filter(
        direction=CashFlowRecord.Direction.OUTFLOW,
        transaction_date__gte=today - timedelta(days=90),
        transaction_date__lt=today,
    ).aggregate(total=Sum('amount'))['total'] or 0)
    avg_daily_expense = total_outflow_90d / 90

    balance = opening_balance() if start_balance is None else start_balance
    opening = balance

    buckets = []  # (label, income, expense)
    for i in range(horizon_days):
        day = today + timedelta(days=i)
        income = plan_by_date.get(day, 0) * execution_rate * factors['income']
        expense = avg_daily_expense * factors['expense']
        if group == 'week':
            week_start = day - timedelta(days=day.weekday())
            if buckets and buckets[-1][0] == week_start.isoformat():
                label, inc, exp = buckets[-1]
                buckets[-1] = (label, inc + income, exp + expense)
                continue
            buckets.append((week_start.isoformat(), income, expense))
        else:
            buckets.append((day.isoformat(), income, expense))

    result = {
        'labels': [], 'projected_income': [], 'projected_expense': [],
        'net_cf': [], 'balance': [], 'gap_dates': [],
    }
    for label, income, expense in buckets:
        net = income - expense
        balance += net
        result['labels'].append(label)
        result['projected_income'].append(round(income, 2))
        result['projected_expense'].append(round(expense, 2))
        result['net_cf'].append(round(net, 2))
        result['balance'].append(round(balance, 2))
        if balance < 0:
            result['gap_dates'].append(label)

    result.update({
        'opening_balance': round(opening, 2),
        'execution_rate': round(execution_rate, 3),
        'group': group,
        'scenario': scenario if scenario in SCENARIOS else 'base',
        'scenario_label': factors['label'],
    })
    return result
