# TRC BPM — Sprint 2 (Phase 6 BE — Дашборды Backend)

**Ветка:** `sprint`  
**Базируется от:** `sprint` (все Phase 5 задачи выполнены и влиты)  
**Цель:** реализовать backend финансовых дашбордов → прогресс ~70% → ~78%

---

## Что уже сделано (не трогать)

### Phase 5 — ПОЛНОСТЬЮ ЗАКРЫТА ✅
- BE-2.fix ✅ — companies.html + positions.html
- BE-2.21 ✅ — Celery hr_check_expirations (ежедневно 06:00)
- BE-5.1–5.11 ✅ — все финансовые модели и views
- BE-5.12 ✅ — CreditModel (сценарии + DSCR)
- BE-5.13 ✅ — ExchangeRate + Celery НБ РК (ежедневно 14:00)
- BE-5.14 ✅ — Отправка счетов email/мессенджеры
- FE-5.1–5.5 ✅ — все финансовые шаблоны
- COLLAB-3 ✅ — стыковка финансов core

### Структура проекта
- **Стек:** Django 4.2 + DRF + Celery + PostgreSQL + Redis + Bootstrap 5 + Vanilla JS
- **Финансы:** `backend/apps/finances/` — models.py, views.py, urls.py, tests.py, admin.py
- **Сервисы:** `backend/apps/finances/services/` — nbrk.py, notifications.py
- **Шаблоны:** `backend/templates/site/finances/`
- **Статика:** `backend/static/site/css/apps/finances.scss`, `backend/static/site/js/apps/`
- **Роли:** `backend/apps/account/role_permissions.py` (Owner, CFO, ChiefAccountant, Administrator)
- **Permissions:** FINANCE_DASHBOARD, FINANCE_BUDGET, FINANCE_SCENARIOS, FINANCE_REPORTS, FINANCE_INVOICES, FINANCE_REGISTERS

### Ключевые модели (все в `backend/apps/finances/models.py`)
- `TenantPaymentRegistry` — реестр платежей арендаторов (status: paid/partial/pending/overdue/cancelled)
- `PaymentCalendarEntry` — календарь платежей (status: plan/fact/overdue, expected_date, actual_amount)
- `GeneratedInvoice` — счета (status: created/sent/viewed/paid/cancelled)
- `BudgetCategory` + `BudgetItem` — бюджетирование (plan/fact/forecast по категориям)
- `FinancialStatement` — ОПиУ (revenue, ebitda, operating_profit, net_profit)
- `CashFlowRecord` — ДДС (amount, flow_type: income/expense, category FK, onec_id)
- `CreditModel` — кредитная модель (scenario: base/stress/optimistic, DSCR)
- `ExchangeRate` — курсы валют (currency, date, rate, метод convert())

### Существующие views (backend/apps/finances/views.py)
- `payment_reg`, `payment_calendar`, `payment_calendar_day`
- `invoice_list`, `invoice_create`, `invoice_detail`, `invoice_edit`, `invoice_send`, etc.
- `budget_list`, `budget`, `budget_create`
- `financial_statement`, `cashflow_register`
- `credit_model_list`, `credit_model_create`

---

## Задачи Спринта 2

### Порядок выполнения (строгий!)
```
BE-6.4 и BE-6.1 — параллельно (не зависят друг от друга)
BE-6.2 и BE-6.3 — после BE-6.1
BE-6.5 — независимо
BE-6.6 — после BE-6.5
BE-6.7, BE-6.8, BE-6.9 — после предыдущих
```

---

### BE-6.4 — Backend аналитики аренды (5h)
**Статус:** ❌  
**Ветка:** `feature/TASK-6.4-rent-analytics-api`  
**Файлы:**
- `backend/apps/finances/views.py` — добавить view
- `backend/apps/finances/urls.py` — добавить URL
- `backend/apps/finances/tests.py` — тесты

**Что сделать:**

View `rent_analytics(request)` → GET `/finances/analytics/rent/`

Возвращает `render()` с контекстом (не JSON — это SSR-шаблон):
```python
context = {
    'top_tenants': [...],       # ТОП-10 по выручке YTD
    'vacancy_rate': 8.5,        # % вакантных площадей
    'avg_rate_per_sqm': 12500,  # средняя ставка тг/м²
    'top_debtors': [...],       # ТОП должников (overdue)
    'rent_dynamics': {          # динамика за 6 мес
        'labels': ['2026-01', ...],
        'actual': [8200000, ...]
    },
    'total_revenue_ytd': ...,
    'total_overdue': ...,
}
```

Расчёты из `TenantPaymentRegistry`:
- `top_tenants` — группировка по `tenant`, сумма `paid` за текущий год, сортировка desc, топ-10
- `vacancy_rate` — если у `Tenant` есть поле `area` (м²), считать долю вакантных. Если поля нет — ставить 0
- `top_debtors` — `TenantPaymentRegistry.objects.filter(status='overdue')`, группировка по tenant, сумма долга
- `rent_dynamics` — группировка по `period` (DateField), sum `paid`, последние 6 периодов

Добавить в `urls.py`:
```python
path('analytics/rent/', views.rent_analytics, name='rent_analytics'),
```

Добавить в меню (`role_permissions.py`) для Owner/CFO/ChiefAccountant/Administrator.

Написать тесты: `RentAnalyticsViewTest` — 200 статус, контекст содержит нужные ключи, фильтрация по периоду.

---

### BE-6.1 — Executive Dashboard Backend (6h)
**Статус:** ❌  
**Ветка:** `feature/TASK-6.1-dashboard-backend`  
**Файлы:**
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

Два endpoint-а:

**1. View `dashboard(request)` → GET `/finances/dashboard/`**

SSR-шаблон с контекстом:
```python
context = {
    'cash_balance': Decimal,       # сумма actual_amount за 90 дней, status=fact
    'revenue_mtd': Decimal,        # TenantPaymentRegistry.paid за текущий месяц
    'revenue_ytd': Decimal,        # за текущий год
    'revenue_mtd_change': float,   # % изменение vs прошлый месяц
    'expenses_mtd': Decimal,       # CashFlowRecord flow_type=expense за месяц
    'net_cf': Decimal,             # revenue_mtd - expenses_mtd
    'budget_deviation_pct': float, # (fact-plan)/plan*100 по BudgetItem
    'overdue_count': int,
    'overdue_amount': Decimal,
    'today': date.today(),
}
```

**2. JSON endpoint `dashboard_kpi(request)` → GET `/finances/dashboard/kpi/`**

Возвращает `JsonResponse` с теми же данными (для AJAX-обновления FE):
```python
return JsonResponse({
    'cash_balance': float(cash_balance),
    'revenue_mtd': float(revenue_mtd),
    'revenue_ytd': float(revenue_ytd),
    'revenue_mtd_change': revenue_mtd_change,
    'expenses_mtd': float(expenses_mtd),
    'net_cf': float(net_cf),
    'budget_deviation_pct': budget_deviation_pct,
    'overdue_count': overdue_count,
    'overdue_amount': float(overdue_amount),
})
```

Добавить drill-down endpoint `dashboard_drilldown(request)` → GET `/finances/dashboard/drilldown/`

Принимает `?type=revenue|expenses|overdue|budget&period=2026-05`.
Возвращает `JsonResponse` со списком записей для детализации:
- `type=revenue` → список `TenantPaymentRegistry` за период
- `type=expenses` → список `CashFlowRecord` flow_type=expense за период
- `type=overdue` → список `TenantPaymentRegistry` status=overdue
- `type=budget` → список `BudgetItem` с отклонением

Добавить в `urls.py`:
```python
path('dashboard/', views.dashboard, name='dashboard'),
path('dashboard/kpi/', views.dashboard_kpi, name='dashboard_kpi'),
path('dashboard/drilldown/', views.dashboard_drilldown, name='dashboard_drilldown'),
```

Тесты: `DashboardViewTest` — 200, контекст, JSON структура. `DashboardDrilldownTest` — все 4 типа.

---

### BE-6.2 — CF chart endpoints (3h)
**Статус:** ❌ (зависит от BE-6.1)  
**Ветка:** `feature/TASK-6.2-cashflow-charts-api`  
**Файлы:**
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

```python
# GET /finances/dashboard/cashflow-daily/?days=30|60|90
def cashflow_daily(request):
    days = int(request.GET.get('days', 30))
    # CashFlowRecord за последние N дней, группировка по date
    # Возвращает JsonResponse
    return JsonResponse({
        'labels': ['2026-05-01', ...],
        'income': [1200000, ...],
        'expense': [900000, ...],
        'net': [300000, ...],   # income - expense
    })

# GET /finances/dashboard/cashflow-weekly/?weeks=12
def cashflow_weekly(request):
    weeks = int(request.GET.get('weeks', 12))
    # Группировка по неделям
    ...
```

Источник данных: `CashFlowRecord` + `PaymentCalendarEntry` (status=fact).

Добавить в `urls.py`:
```python
path('dashboard/cashflow-daily/', views.cashflow_daily, name='cashflow_daily'),
path('dashboard/cashflow-weekly/', views.cashflow_weekly, name='cashflow_weekly'),
```

Тесты: структура ответа (labels/income/expense/net), параметр days, пустые данные → пустые массивы.

---

### BE-6.3 — Drill-down до документа 1С (4h)
**Статус:** ❌ (зависит от BE-6.1)  
**Ветка:** `feature/TASK-6.3-drilldown-api`  
**Файлы:**
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

Endpoint для детализации операции 1С по `onec_id`:

```python
# GET /finances/dashboard/drilldown/record/<onec_id>/
def drilldown_record(request, onec_id):
    # Ищем CashFlowRecord с этим onec_id
    record = get_object_or_404(CashFlowRecord, onec_id=onec_id)
    # Ищем связанного контрагента в onec приложении
    from onec.models import Counterparty  # если модель там
    counterparty = None
    try:
        counterparty = Counterparty.objects.filter(id_1c=onec_id).first()
    except Exception:
        pass

    return JsonResponse({
        'record': {
            'id': record.id,
            'date': str(record.date),
            'amount': float(record.amount),
            'flow_type': record.flow_type,
            'description': getattr(record, 'description', ''),
            'onec_id': record.onec_id,
        },
        'counterparty_url': f'/onec/counterparties/{counterparty.pk}/' if counterparty else None,
        'counterparty_name': counterparty.full_name if counterparty else None,
    })
```

Добавить в `urls.py`:
```python
path('dashboard/drilldown/record/<str:onec_id>/', views.drilldown_record, name='drilldown_record'),
```

Тесты: 200 со связанным контрагентом, 200 без контрагента, 404 для несуществующего onec_id.

---

### BE-6.5 — Backend прогноза CF (6h)
**Статус:** ❌  
**Ветка:** `feature/TASK-6.5-forecast-api`  
**Файлы:**
- `backend/apps/finances/services/forecast.py` — создать
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

Сервис `backend/apps/finances/services/forecast.py`:
```python
from datetime import date, timedelta
from decimal import Decimal
from .models import PaymentCalendarEntry, CashFlowRecord

def forecast_cashflow(horizon_days: int = 90):
    """
    Прогноз CF на horizon_days дней вперёд.
    Алгоритм:
    1. Берём PaymentCalendarEntry status=plan за ближайшие horizon_days дней
    2. Считаем средний % исполнения из исторических fact (actual_amount/expected_amount)
    3. Прогнозируем ожидаемые поступления
    4. Добавляем CashFlowRecord ожидаемые расходы (из повторяющихся записей)
    5. Выявляем точки кассового разрыва (net_cf < 0)
    Возвращает: {labels, projected_income, projected_expense, net_cf, gap_dates}
    """
    today = date.today()
    end_date = today + timedelta(days=horizon_days)
    ...
```

View:
```python
# GET /finances/dashboard/forecast/?days=30|60|90
def cashflow_forecast(request):
    days = int(request.GET.get('days', 90))
    data = forecast_cashflow(horizon_days=days)
    return JsonResponse(data)
```

Добавить в `urls.py`:
```python
path('dashboard/forecast/', views.cashflow_forecast, name='cashflow_forecast'),
```

Тесты: `ForecastServiceTest` — структура ответа, gap_dates правильно определяются, горизонт 30/60/90 дней.

---

### BE-6.6 — Backend сценариев (5h)
**Статус:** ❌ (зависит от BE-6.5)  
**Ветка:** `feature/TASK-6.6-scenarios-api`  
**Файлы:**
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/forms.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

View для сравнения сценариев CreditModel (только CFO):
```python
# GET /finances/scenarios/
@need_permission(PermissionEnums.FINANCE_SCENARIOS)
def scenarios_list(request):
    scenarios = CreditModel.objects.all().order_by('-created_at')
    comparison = []
    for s in scenarios:
        s.calculate_dscr()
        comparison.append({
            'obj': s,
            'dscr': s.dscr,
            'free_cashflow': s.free_cashflow,
            'risk_level': s.risk_level,
        })
    return render(request, 'site/finances/scenarios.html', {'comparison': comparison})

# GET /finances/scenarios/<pk>/json/ — JSON для графика
def scenario_detail_json(request, pk):
    scenario = get_object_or_404(CreditModel, pk=pk)
    return JsonResponse({
        'name': scenario.name,
        'scenario': scenario.scenario,
        'projected_cashflow': scenario.projected_cashflow,
        'dscr': float(scenario.dscr or 0),
        'risk_level': scenario.risk_level,
    })
```

Добавить в `urls.py`:
```python
path('scenarios/', views.scenarios_list, name='scenarios_list'),
path('scenarios/<int:pk>/json/', views.scenario_detail_json, name='scenario_detail_json'),
```

Добавить в меню для Owner/CFO.

Тесты: 200 для CFO, 403 для ChiefAccountant, JSON-структура.

---

### BE-6.7 — Excel-export финансовых отчётов (5h)
**Статус:** ❌  
**Ветка:** `feature/TASK-6.7-excel-export`  
**Файлы:**
- `backend/apps/finances/services/excel.py` — создать
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

Сервис `backend/apps/finances/services/excel.py` с функциями:
```python
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from django.http import HttpResponse

def export_payment_registry(queryset) -> HttpResponse:
    """Экспорт TenantPaymentRegistry в Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Реестр оплат'
    headers = ['Арендатор', 'Договор', 'Период', 'Начислено', 'Оплачено', 'Баланс', 'Статус']
    # ... заполнить данные, стилизовать
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="payment_registry.xlsx"'
    wb.save(response)
    return response

def export_budget(queryset) -> HttpResponse: ...
def export_cashflow(queryset) -> HttpResponse: ...
def export_financial_statement(queryset) -> HttpResponse: ...
```

Добавить в views кнопки экспорта (если `?export=xlsx` в GET):
```python
# В payment_reg view:
if request.GET.get('export') == 'xlsx':
    return export_payment_registry(qs)
```

То же самое для: `cashflow_register`, `budget_list`, `financial_statement`.

Добавить в шаблоны кнопку «Экспорт Excel» (уже есть в финансовых шаблонах — проверить).

Тесты: response Content-Type, Content-Disposition, статус 200.

---

### BE-6.8 — Глобальные финансовые фильтры (3h)
**Статус:** ❌  
**Ветка:** `feature/TASK-6.8-finance-filters`  
**Файлы:**
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

Сохранение и применение глобальных фильтров через сессию:
```python
# POST /finances/filters/save/ — сохранить фильтры в session
def save_finance_filters(request):
    if request.method == 'POST':
        import json
        filters = json.loads(request.body)
        request.session['finance_filters'] = {
            'company': filters.get('company', ''),
            'tenant': filters.get('tenant', ''),
            'category': filters.get('category', ''),
            'period_from': filters.get('period_from', ''),
            'period_to': filters.get('period_to', ''),
        }
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)

# GET /finances/filters/ — получить текущие фильтры
def get_finance_filters(request):
    filters = request.session.get('finance_filters', {})
    return JsonResponse(filters)
```

Добавить в `urls.py`:
```python
path('filters/save/', views.save_finance_filters, name='save_finance_filters'),
path('filters/', views.get_finance_filters, name='get_finance_filters'),
```

Тесты: сохранение в сессию, получение, пустые фильтры по умолчанию.

---

### BE-6.9 — Мультивалюта backend (3h)
**Статус:** ❌ (зависит от BE-5.13 ✅ и BE-6.1)  
**Ветка:** `feature/TASK-6.9-multi-currency-backend`  
**Файлы:**
- `backend/apps/finances/services/balances.py` — создать
- `backend/apps/finances/views.py`
- `backend/apps/finances/urls.py`
- `backend/apps/finances/tests.py`

**Что сделать:**

Сервис `backend/apps/finances/services/balances.py`:
```python
from .models import ExchangeRate, PaymentCalendarEntry, TenantPaymentRegistry

def get_balances_with_conversion(currency='USD'):
    """
    Возвращает ключевые балансы в KZT и указанной валюте.
    """
    from datetime import date
    today = date.today()
    # Берём курс на сегодня (или последний доступный)
    rate = ExchangeRate.objects.filter(
        currency=currency
    ).order_by('-date').first()

    cash_balance_kzt = # ... считать из PaymentCalendarEntry
    revenue_mtd_kzt = # ... из TenantPaymentRegistry

    return {
        'cash_balance_kzt': float(cash_balance_kzt),
        'cash_balance_foreign': float(ExchangeRate.convert(cash_balance_kzt, 'KZT', currency)) if rate else None,
        'revenue_mtd_kzt': float(revenue_mtd_kzt),
        'revenue_mtd_foreign': float(ExchangeRate.convert(revenue_mtd_kzt, 'KZT', currency)) if rate else None,
        'currency': currency,
        'rate': float(rate.rate) if rate else None,
        'rate_date': str(rate.date) if rate else None,
        'rate_is_fresh': (today - rate.date).days <= 1 if rate else False,
    }
```

View:
```python
# GET /finances/dashboard/balances/?currency=USD|EUR|RUB
def dashboard_balances(request):
    currency = request.GET.get('currency', 'USD')
    data = get_balances_with_conversion(currency=currency)
    return JsonResponse(data)
```

Добавить в `urls.py`:
```python
path('dashboard/balances/', views.dashboard_balances, name='dashboard_balances'),
```

Тесты: ответ содержит rate/rate_date, конвертация правильная, fallback при отсутствии курса.

---

## Итого Спринт 2

| Задача | Ветка | Оценка | Зависит от |
|--------|-------|--------|------------|
| BE-6.4 | feature/TASK-6.4-rent-analytics-api | 5h | — |
| BE-6.1 | feature/TASK-6.1-dashboard-backend | 6h | — |
| BE-6.2 | feature/TASK-6.2-cashflow-charts-api | 3h | BE-6.1 |
| BE-6.3 | feature/TASK-6.3-drilldown-api | 4h | BE-6.1 |
| BE-6.5 | feature/TASK-6.5-forecast-api | 6h | — |
| BE-6.6 | feature/TASK-6.6-scenarios-api | 5h | BE-6.5 |
| BE-6.7 | feature/TASK-6.7-excel-export | 5h | — |
| BE-6.8 | feature/TASK-6.8-finance-filters | 3h | — |
| BE-6.9 | feature/TASK-6.9-multi-currency-backend | 3h | BE-5.13 ✅ |
| **ИТОГО** | | **40h** | |

**После Спринта 2 → ~78%**

---

## Правила

1. **Каждая задача — отдельная ветка** от `sprint` (не от develop)
2. **PR в ветку `sprint`** (base branch = sprint), не в develop
3. **Тесты обязательны** для каждой задачи
4. **Коммит-сообщения:** `BE-6.1: dashboard backend + KPI endpoints`
5. **Декоратор прав:** использовать `@need_permission(PermissionEnums.FINANCE_DASHBOARD)` на views дашборда
6. Смотреть примеры в `backend/apps/finances/views.py` — уже есть паттерны для context + render

---

## Следующий шаг после Спринта 2 — Спринт 3 (Phase 6 FE)

FE-задачи дашбордов (Анель):
- FE-6.1: Executive Dashboard (KPI tiles + Chart.js) — 14h
- FE-6.2: Toggle KZT/USD UI — 3h
- FE-6.3: Аналитика аренды (Pie + Line charts) — 6h
- FE-6.4: Прогноз CF + сценарии (3 линии) — 8h
- FE-6.5: Глобальные фильтры UI — 4h
- COLLAB-4: Стыковка дашбордов — 8h
