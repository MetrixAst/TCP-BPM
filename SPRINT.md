# TRC BPM — Sprint 3 (Phase 6 FE — Дашборды Frontend)

**Ветка:** `sprint`  
**Цель:** реализовать frontend финансовых дашбордов → ~78% → ~85%  
**Исполнитель:** FE (Анель)

---

## Что уже сделано (не трогать)

### Все Phase 5 + Phase 6 BE ✅
- BE-6.1 ✅ — dashboard view + `/finances/dashboard/kpi/` + `/finances/dashboard/drilldown/`
- BE-6.2 ✅ — `/finances/dashboard/cashflow-daily/` + `/finances/dashboard/cashflow-weekly/`
- BE-6.3 ✅ — `/finances/dashboard/drilldown/record/<onec_id>/`
- BE-6.4 ✅ — `/finances/analytics/rent/`
- BE-6.5 ✅ — `/finances/dashboard/forecast/?days=30|60|90`
- BE-6.6 ✅ — `/finances/scenarios/` + `/finances/scenarios/<pk>/json/`
- BE-6.7 ✅ — `?export=xlsx` в реестре, ДДС, бюджете, ОПиУ
- BE-6.8 ✅ — `/finances/filters/save/` + `/finances/filters/`
- BE-6.9 ✅ — `/finances/dashboard/balances/?currency=USD|EUR|RUB`

### Стек и соглашения
- **Шаблоны:** Django Templates SSR, `{% extends "site/base.html" %}`
- **Стили:** `fin-*` CSS-классы из `backend/static/site/css/apps/finances.scss`  
  Переменные: `$fin-primary:#2f6bed`, `$fin-success:#22a85a`, `$fin-danger:#ff3b30`, `$fin-warning:#ff9500`
- **JS:** Vanilla JS + Chart.js (уже подключён глобально через base.html или подключать через `{% block scripts %}`)
- **Иконки:** Bootstrap Icons (`bi bi-*`)
- **Образцы верстки:** `invoice_list.html`, `payment_calendar.html`, `budget_list.html`
- **Каждый шаблон** подключает `finances.css`: `<link rel="stylesheet" href="{% static 'site/css/apps/finances.css' %}?v=...">`

### Правила
1. Ветки от `sprint`, PR в `sprint`
2. Коммиты: `FE-6.1: Executive Dashboard шаблон + Chart.js`
3. Для каждого нового JS-файла — `backend/static/site/js/apps/<name>.js`
4. Новые SCSS-классы — добавлять в `backend/static/site/css/apps/finances.scss`
5. Chart.js подключать: `<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>` в `{% block scripts %}`

---

## Задачи Спринта 3

### Порядок выполнения
```
FE-6.3 и FE-6.5 — независимы, можно начать сразу
FE-6.1 — самый большой (14h), запускать параллельно
FE-6.2 — после FE-6.1
FE-6.4 — после FE-6.1 (использует те же layout-паттерны)
COLLAB-4 — после всех FE-6.x
```

---

### FE-6.1 — Executive Dashboard (14h)
**Статус:** ❌  
**Ветка:** `feature/FE-6.1-executive-dashboard`  
**Файлы:**
- `backend/templates/site/finances/dashboard.html` — уже создан BE (пустой или stub), **переверстать полностью**
- `backend/static/site/js/apps/dashboard.js` — создать
- `backend/static/site/css/apps/finances.scss` — добавить классы `fin-kpi-*`, `fin-chart-*`

**Контекст из view `dashboard(request)`:**
```python
context = {
    'cash_balance': Decimal,         # остаток ДС
    'revenue_mtd': Decimal,          # выручка текущий месяц
    'revenue_ytd': Decimal,          # выручка текущий год
    'revenue_mtd_change': float,     # % изменение vs прошлый месяц (может быть отрицательным)
    'expenses_mtd': Decimal,         # расходы текущий месяц
    'net_cf': Decimal,               # net cash flow = revenue_mtd - expenses_mtd
    'budget_deviation_pct': float,   # % отклонения от бюджета
    'overdue_count': int,            # кол-во просроченных платежей
    'overdue_amount': Decimal,       # сумма просроченных
    'today': date,
}
```

**Что сделать в шаблоне:**

**1. KPI-плитки (6 штук)** — верхняя строка:
```html
<div class="fin-kpi-grid">
  <!-- Остаток ДС -->
  <div class="fin-kpi-card">
    <span class="fin-kpi-label">Остаток ДС</span>
    <span class="fin-kpi-value">{{ cash_balance|floatformat:0 }} ₸</span>
    <span class="fin-kpi-sub">за 90 дней</span>
  </div>
  <!-- Выручка MTD с трендом -->
  <div class="fin-kpi-card">
    <span class="fin-kpi-label">Выручка (месяц)</span>
    <span class="fin-kpi-value">{{ revenue_mtd|floatformat:0 }} ₸</span>
    <span class="fin-kpi-trend {% if revenue_mtd_change >= 0 %}is-up{% else %}is-down{% endif %}">
      {{ revenue_mtd_change|floatformat:1 }}%
    </span>
  </div>
  <!-- Выручка YTD -->
  <!-- Расходы MTD -->
  <!-- Чистый CF -->
  <!-- Просрочка -->
</div>
```

Каждая плитка — кликабельна, открывает drill-down панель. Добавить `data-drill-type="revenue"` и т.д.

**2. Графики Chart.js (2 штуки):**

```html
<div class="fin-chart-grid">
  <div class="fin-chart-card">
    <div class="fin-chart-header">
      <span class="fin-chart-title">Поступления vs Выбытия</span>
      <div class="fin-chart-toggle">
        <button class="fin-chart-btn is-active" data-days="30">30д</button>
        <button class="fin-chart-btn" data-days="60">60д</button>
        <button class="fin-chart-btn" data-days="90">90д</button>
      </div>
    </div>
    <canvas id="cashflowChart" height="200"></canvas>
  </div>
  <div class="fin-chart-card">
    <div class="fin-chart-header">
      <span class="fin-chart-title">Недельный CF</span>
    </div>
    <canvas id="weeklyChart" height="200"></canvas>
  </div>
</div>
```

**3. Drill-down панель (sidebar):**
```html
<aside class="fin-drill-panel" id="drillPanel" aria-hidden="true">
  <div class="fin-drill-panel__overlay" data-close-drill></div>
  <div class="fin-drill-panel__content">
    <div class="fin-drill-panel__header">
      <h2 id="drillTitle">—</h2>
      <button data-close-drill class="fin-day-panel__close"><i class="bi bi-x-lg"></i></button>
    </div>
    <div id="drillBody" class="fin-drill-body">
      <div class="fin-empty">Загрузка...</div>
    </div>
  </div>
</aside>
```

**4. Мультивалютный тоггл (вверху страницы):**
```html
<div class="fin-currency-toggle">
  <span class="fin-currency-label">KZT</span>
  <select id="currencySelect" class="fin-input" style="width:auto">
    <option value="">KZT</option>
    <option value="USD">USD</option>
    <option value="EUR">EUR</option>
    <option value="RUB">RUB</option>
  </select>
  <span id="rateHint" class="fin-currency-rate"></span>
</div>
```

**`dashboard.js` — основной JS:**
```javascript
// 1. Загрузить графики при старте
async function loadCashflowChart(days = 30) {
  const resp = await fetch(`/finances/dashboard/cashflow-daily/?days=${days}`);
  const data = await resp.json();
  // Создать/обновить Chart.js Bar chart
  // income — синий, expense — красный, net — серый линия
  // Отрицательные значения net подсвечивать красным
}

async function loadWeeklyChart(weeks = 12) {
  const resp = await fetch(`/finances/dashboard/cashflow-weekly/?weeks=${weeks}`);
  const data = await resp.json();
  // Line chart
}

// 2. Drill-down
async function openDrillPanel(type, period) {
  const resp = await fetch(`/finances/dashboard/drilldown/?type=${type}&period=${period}`);
  const data = await resp.json();
  // Заполнить drillBody таблицей с данными
  // Для каждой записи с onec_id — кликабельная ссылка
}

// 3. KPI refresh (AJAX, каждые 5 минут)
async function refreshKPIs() {
  const resp = await fetch('/finances/dashboard/kpi/');
  const data = await resp.json();
  // Обновить значения в плитках без перезагрузки
}

// 4. Мультивалюта
async function loadBalances(currency) {
  const resp = await fetch(`/finances/dashboard/balances/?currency=${currency}`);
  const data = await resp.json();
  // Показать курс рядом с тогглом
  // Обновить значения cash_balance и revenue в KZT + в валюте
}

document.addEventListener('DOMContentLoaded', () => {
  loadCashflowChart(30);
  loadWeeklyChart(12);
  // toggle handlers, drill panel handlers, KPI refresh interval
});
```

**Новые SCSS-классы для `finances.scss`:**
```scss
.fin-kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  @media (max-width: 768px) { grid-template-columns: 1fr 1fr; }
}
.fin-kpi-card {
  background: $fin-card-bg;
  border: 1px solid $fin-border;
  border-radius: 8px;
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.15s;
  &:hover { border-color: $fin-primary; }
}
.fin-kpi-label { font-size: 12px; color: $fin-muted; display: block; }
.fin-kpi-value { font-size: 24px; font-weight: 600; color: $fin-text; display: block; margin: 4px 0; }
.fin-kpi-sub   { font-size: 11px; color: $fin-muted; }
.fin-kpi-trend { font-size: 12px; font-weight: 600;
  &.is-up   { color: $fin-success; }
  &.is-down { color: $fin-danger; }
}
.fin-chart-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-top: 20px; }
.fin-chart-card { background: $fin-card-bg; border: 1px solid $fin-border; border-radius: 8px; padding: 20px; }
.fin-chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.fin-chart-title  { font-weight: 600; font-size: 14px; color: $fin-text; }
.fin-chart-toggle { display: flex; gap: 4px; }
.fin-chart-btn    { padding: 4px 10px; font-size: 12px; border: 1px solid $fin-border; border-radius: 4px; background: none; cursor: pointer; color: $fin-muted;
  &.is-active { background: $fin-primary; color: #fff; border-color: $fin-primary; }
}
.fin-drill-panel {
  position: fixed; top: 0; right: -480px; width: 480px; height: 100vh;
  background: $fin-card-bg; border-left: 1px solid $fin-border; z-index: 1000;
  transition: right 0.25s ease; display: flex; flex-direction: column;
  &.is-open { right: 0; }
  &__overlay { position: fixed; inset: 0; background: rgba(0,0,0,.25); display: none; }
  &.is-open &__overlay { display: block; }
  &__content { display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
  &__header { padding: 20px; border-bottom: 1px solid $fin-border; display: flex; justify-content: space-between; align-items: center; }
}
.fin-drill-body { padding: 16px; flex: 1; }
.fin-currency-toggle { display: flex; align-items: center; gap: 8px; }
.fin-currency-rate   { font-size: 11px; color: $fin-muted; }
```

---

### FE-6.2 — Toggle KZT/USD на дашборде (3h)
**Статус:** ❌ (зависит от FE-6.1)  
**Ветка:** `feature/FE-6.2-multi-currency-ui`  
**Файлы:**
- `backend/templates/site/finances/dashboard.html` — расширить (уже создан в FE-6.1)
- `backend/static/site/js/apps/dashboard.js` — расширить `loadBalances()`

**Endpoint:** `GET /finances/dashboard/balances/?currency=USD`  
**Ответ:**
```json
{
  "cash_balance_kzt": 45000000,
  "cash_balance_foreign": 95000,
  "revenue_mtd_kzt": 12500000,
  "revenue_mtd_foreign": 26455,
  "currency": "USD",
  "rate": 473.5,
  "rate_date": "2026-05-21",
  "rate_is_fresh": true
}
```

**Что сделать:**
- При выборе валюты из select (`currencySelect`) — вызывать `loadBalances(currency)`
- Обновлять плитки "Остаток ДС" и "Выручка MTD" — показывать **оба значения** (KZT основное + валюта мелко)
- Рядом с тогглом показывать: `Курс: 473.5 ₸ / USD на 21.05.2026`
- Если `rate_is_fresh = false` — показывать баннер: `Курс устарел (последний: ...)` в `.fin-currency-rate.is-stale`

---

### FE-6.3 — Аналитика аренды (6h)
**Статус:** ❌  
**Ветка:** `feature/FE-6.3-rent-analytics-template`  
**Файлы:**
- `backend/templates/site/finances/rent_analytics.html` — **переверстать** (stub от BE)
- `backend/static/site/js/apps/rent-analytics.js` — создать

**Контекст из view `rent_analytics(request)`:**
```python
context = {
    'top_tenants': [{'tenant': obj, 'total_paid': Decimal}, ...],   # ТОП-10
    'vacancy_rate': float,        # % вакантности
    'avg_rate_per_sqm': float,    # тг/м²
    'top_debtors': [{'tenant': obj, 'total_debt': Decimal}, ...],
    'total_revenue_ytd': float,
    'total_overdue': float,
    'rent_dynamics': {'labels': [...], 'actual': [...]},
}
```

**Что сделать:**

**1. KPI-строка (3 плитки):**
- Вакантность: `{{ vacancy_rate }}%`
- Средняя ставка: `{{ avg_rate_per_sqm|floatformat:0 }} ₸/м²`
- Просрочка: `{{ total_overdue|floatformat:0 }} ₸`

**2. Два графика Chart.js (Pie + Line) в сетке:**

`rent-analytics.js`:
```javascript
// Pie chart — доли арендаторов в выручке
function renderTenantPie(data) {
  // data.labels = [tenant names], data.values = [amounts]
  // из top_tenants через data-атрибуты или JSON в <script type="application/json">
  new Chart(document.getElementById('tenantPieChart'), {
    type: 'doughnut',
    data: { labels: data.labels, datasets: [{ data: data.values, backgroundColor: [...] }] },
    options: { plugins: { legend: { position: 'right' } } }
  });
}

// Line chart — динамика поступлений за 6 мес
function renderDynamicsChart(dynamics) {
  new Chart(document.getElementById('dynamicsChart'), {
    type: 'line',
    data: {
      labels: dynamics.labels,
      datasets: [{ label: 'Поступления', data: dynamics.actual,
        borderColor: '#2f6bed', backgroundColor: 'rgba(47,107,237,0.1)', fill: true }]
    }
  });
}
```

Передавать данные в JS через JSON в шаблоне:
```html
<script type="application/json" id="tenantData">
  {"labels": [{% for t in top_tenants %}"{{ t.tenant.name }}"{% if not forloop.last %},{% endif %}{% endfor %}],
   "values": [{% for t in top_tenants %}{{ t.total_paid|floatformat:0 }}{% if not forloop.last %},{% endif %}{% endfor %}]}
</script>
```

**3. Таблица ТОП должников:**
```html
<table class="fin-table">
  <thead><tr><th>Арендатор</th><th>Долг</th><th>Статус</th></tr></thead>
  <tbody>
    {% for d in top_debtors %}
    <tr class="fin-row fin-row--danger">
      <td>{{ d.tenant.name }}</td>
      <td><strong>{{ d.total_debt|floatformat:0 }} ₸</strong></td>
      <td><span class="fin-status fin-status--danger">Просрочен</span></td>
    </tr>
    {% empty %}
    <tr><td colspan="3" class="fin-empty">Должников нет</td></tr>
    {% endfor %}
  </tbody>
</table>
```

---

### FE-6.4 — Прогноз CF + Сценарии (8h)
**Статус:** ❌  
**Ветка:** `feature/FE-6.4-forecast-scenarios`  
**Файлы:**
- `backend/templates/site/finances/dashboard.html` — добавить секцию прогноза (или отдельная страница)
- `backend/templates/site/finances/scenarios.html` — **переверстать** (stub от BE)
- `backend/static/site/js/apps/forecast.js` — создать

**Endpoint прогноза:** `GET /finances/dashboard/forecast/?days=30|60|90`  
**Ответ:**
```json
{
  "labels": ["2026-05-22", ...],
  "projected_income": [1200000, ...],
  "projected_expense": [900000, ...],
  "net_cf": [300000, ...],
  "gap_dates": ["2026-06-03", ...]   // дни кассового разрыва (net_cf < 0)
}
```

**`forecast.js`:**
```javascript
async function loadForecast(days = 90) {
  const resp = await fetch(`/finances/dashboard/forecast/?days=${days}`);
  const data = await resp.json();

  // Line chart с 3 линиями: доходы (синий), расходы (красный), net (серый)
  // gap_dates — точки с net_cf < 0 подсвечивать красными маркерами
  const gapSet = new Set(data.gap_dates);
  const pointColors = data.labels.map((label, i) =>
    data.net_cf[i] < 0 ? '#ff3b30' : '#22a85a'
  );

  new Chart(document.getElementById('forecastChart'), {
    type: 'line',
    data: {
      labels: data.labels,
      datasets: [
        { label: 'Прогноз поступлений', data: data.projected_income, borderColor: '#2f6bed', fill: false },
        { label: 'Прогноз расходов',    data: data.projected_expense, borderColor: '#ff3b30', fill: false },
        { label: 'Чистый CF',           data: data.net_cf, borderColor: '#7b7890',
          pointBackgroundColor: pointColors, pointRadius: 5, fill: false }
      ]
    },
    options: {
      plugins: {
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString('ru')} ₸` } }
      }
    }
  });

  // Вывести ближайший gap_date если есть
  if (data.gap_dates.length > 0) {
    document.getElementById('gapAlert').textContent =
      `Ближайший кассовый разрыв: ${data.gap_dates[0]}`;
    document.getElementById('gapAlert').style.display = 'block';
  }
}
```

**`scenarios.html` — список сценариев (контекст из BE-6.6):**
```python
context = {
    'models': CreditModel queryset,
    'can_manage': bool,   # True для CFO/Owner
}
```

**Endpoint сценария:** `GET /finances/scenarios/<pk>/json/`  
Возвращает projected_cashflow + DSCR для графика.

Шаблон:
- Таблица сравнения: Название / Сценарий / DSCR / Free CF / Risk Level / badge цветом
- Для каждого сценария — кнопка «Показать на графике» → загружает JSON и рисует Line chart
- Только `can_manage` видит кнопку «Создать» (ссылка на `credit_model_create`)

---

### FE-6.5 — Глобальные финансовые фильтры (4h)
**Статус:** ❌  
**Ветка:** `feature/FE-6.5-finance-filters-ui`  
**Файлы:**
- `backend/templates/site/components/finance_filters.html` — создать
- `backend/static/site/js/apps/finance-filters.js` — создать

**Endpoints:**
- `POST /finances/filters/save/` (JSON body) — сохранить в сессию
- `GET /finances/filters/` — получить текущие

**`finance_filters.html` — универсальный компонент:**
```html
{% load static %}
<section class="fin-filter-card fin-global-filter">
  <form id="globalFilterForm" class="fin-filter-form">
    {% csrf_token %}
    <div class="fin-field">
      <label class="fin-label">Арендатор</label>
      <div class="fin-custom-select" data-filter-key="tenant">
        <input type="hidden" name="tenant" value="">
        <button type="button" class="fin-custom-select__button">
          <span class="fin-custom-select__value">Все</span>
          <span class="fin-custom-select__arrow"></span>
        </button>
        <div class="fin-custom-select__dropdown">
          <!-- tenants — передавать через include context или отдельный AJAX -->
        </div>
      </div>
    </div>
    <div class="fin-field fin-field--date">
      <label class="fin-label">Период с</label>
      <input type="date" name="period_from" class="fin-input fin-date-input" data-filter-key="period_from">
    </div>
    <div class="fin-field fin-field--date">
      <label class="fin-label">По</label>
      <input type="date" name="period_to" class="fin-input fin-date-input" data-filter-key="period_to">
    </div>
    <button type="button" id="applyGlobalFilters" class="fin-btn fin-btn--primary">Применить</button>
    <button type="button" id="resetGlobalFilters" class="fin-btn fin-btn--light">Сбросить</button>
  </form>
</section>
```

**`finance-filters.js`:**
```javascript
async function loadSavedFilters() {
  const resp = await fetch('/finances/filters/');
  const filters = await resp.json();
  // Заполнить поля формы из сессии
  Object.entries(filters).forEach(([key, value]) => {
    const el = document.querySelector(`[data-filter-key="${key}"]`);
    if (el) el.value = value;
  });
}

async function saveFilters(filters) {
  await fetch('/finances/filters/save/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
    body: JSON.stringify(filters)
  });
}

document.getElementById('applyGlobalFilters')?.addEventListener('click', async () => {
  const filters = {};
  document.querySelectorAll('[data-filter-key]').forEach(el => {
    filters[el.dataset.filterKey] = el.value;
  });
  await saveFilters(filters);
  window.location.reload();  // перезагрузить страницу с фильтрами
});

document.getElementById('resetGlobalFilters')?.addEventListener('click', async () => {
  await saveFilters({});
  window.location.reload();
});

document.addEventListener('DOMContentLoaded', loadSavedFilters);
```

Добавить `{% include 'site/components/finance_filters.html' %}` в:
- `dashboard.html`
- `payment_register.html`
- `cashflow.html`

---

### COLLAB-4 — Стыковка дашбордов (8h)
**Статус:** ❌ (после всех FE-6.x)  
**Ветка:** `feature/COLLAB-4-dashboards`  

**Что проверить:**
1. Dashboard: KPI плитки загружаются, графики рисуются, drill-down открывается
2. Мультивалюта: toggle USD/EUR/RUB обновляет плитки, курс отображается
3. Аналитика аренды: Pie chart и Line chart работают с реальными данными
4. Прогноз CF: горизонт 30/60/90 переключается, gap_dates отображаются красным
5. Сценарии: таблица сравнения, график по сценарию, права CFO/Owner
6. Глобальные фильтры: сохраняются в сессию, применяются при перезагрузке
7. Excel-export: кнопка на каждом финансовом экране скачивает файл
8. Мобильная адаптивность: `@media (max-width: 768px)` на всех экранах
9. Права по ролям: CFO видит сценарии и бюджет CRUD, ChiefAccountant — read-only

**Исправить все расхождения между BE-контекстом и шаблонами.**

---

## Итого Спринт 3

| Задача | Ветка | Оценка | Зависит от |
|--------|-------|--------|------------|
| FE-6.1 | feature/FE-6.1-executive-dashboard | 14h | — |
| FE-6.2 | feature/FE-6.2-multi-currency-ui | 3h | FE-6.1 |
| FE-6.3 | feature/FE-6.3-rent-analytics-template | 6h | — |
| FE-6.4 | feature/FE-6.4-forecast-scenarios | 8h | — |
| FE-6.5 | feature/FE-6.5-finance-filters-ui | 4h | — |
| COLLAB-4 | feature/COLLAB-4-dashboards | 8h | все выше |
| **ИТОГО** | | **43h** | |

**После Спринта 3 → ~85%**

---

## После Спринта 3 — Спринт 4 (Phase 7: Финализация)

BE-задачи (Дарья):
- BE-7.1: Единое REST API DRF (Tasks + HR + Finances) — 8h
- BE-7.2: JWT аутентификация — 3h
- BE-7.3: Swagger / OpenAPI — 3h
- BE-7.4: Тесты coverage > 70% — 10h
- BE-7.5: Docker + production deployment — 5h
- BE-7.6: CI/CD GitHub Actions — 4h
- BE-7.7: Audit trail (AuditLog + middleware) — 8h
- COLLAB-5: UAT сценарии на staging — 12h

**После Спринта 4 → ~100%**
