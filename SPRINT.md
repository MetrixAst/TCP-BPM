# TRC BPM — Sprint (Phase 5 остаток → 70%)

**Ветка:** `sprint`  
**Базируется от:** `develop` (последний коммит: #66 TASK-5.11 budget views)  
**Цель:** закрыть оставшиеся задачи Phase 5, хвосты Phase 2 → прогресс ~58% → ~70%

---

## Контекст проекта

- **Стек:** Django 4.2 + DRF + Celery + PostgreSQL + Redis + Bootstrap 5 + Vanilla JS
- **Репо:** `backend/` — Django-приложение, `backend/apps/` — модули
- **Финансы:** `backend/apps/finances/` — модели, views, urls, tests, admin
- **HR:** `backend/apps/hr/` — модели, views, urls, tasks
- **Шаблоны:** `backend/templates/site/`
- **Статика:** `backend/static/site/css/apps/`, `backend/static/site/js/apps/`
- **Роли:** Owner, CFO, ChiefAccountant, Administrator, HR, Staff (в `backend/apps/account/role_permissions.py`)
- **Все задачи должны иметь тесты** в соответствующем `tests.py`
- **Каждая задача — отдельный коммит** с понятным сообщением

---

## Что уже сделано (не трогать)

- ✅ BE-5.1–5.11: роли, модели (TenantPaymentRegistry, PaymentCalendarEntry, GeneratedInvoice, BudgetCategory, BudgetItem, FinancialStatement, CashFlowRecord), views реестра/календаря/счетов/бюджета
- ✅ FE-5.1–5.3: шаблоны реестра, календаря, счетов (merged в develop)
- ✅ Phase 4 (1С): Counterparty, Invoice, DRF API, Celery sync — всё в `backend/apps/onec/`
- ✅ Phase 2 BE-2.9–2.20: HR полностью (отпуска, посещаемость, документы, допуски, сертификации)

---

## Задачи спринта

### BE-2.fix — Починить пустые шаблоны (1h)
**Статус:** ❌ не сделано  
**Ветка:** `feature/BE-2.fix-templates`  
**Файлы:**
- `backend/templates/site/hr/companies.html` — сейчас пустой (0 байт)
- `backend/templates/site/hr/positions.html` — сейчас пустой (0 байт)

**Что сделать:**
Создать минимальные рабочие шаблоны. Смотреть на существующие HR-шаблоны как образец (например `backend/templates/site/hr/employees.html`).

`companies.html` — таблица компаний: name, bin_number, address, phone, email, кол-во сотрудников. Кнопка создать (если есть права).

`positions.html` — таблица должностей: title, department, кол-во сотрудников.

---

### BE-2.21 — Celery задача проверки истечений HR (3h)
**Статус:** ❌ не сделано  
**Ветка:** `feature/TASK-2.21-hr-expiration-checker`  
**Файлы:**
- `backend/apps/hr/tasks.py` — создать если нет
- `backend/project/settings.py` — добавить в CELERY_BEAT_SCHEDULE

**Что сделать:**
Celery task `hr_check_expirations` — запускается ежедневно в 06:00.

Проверяет:
- `EmployeeDocument` — active → expiring (за 30 дней до истечения), active/expiring → expired (просроченные)
- `EmployeeWorkPermit` — то же самое
- `EmployeeCertification` — то же самое

Статусы брать из существующих энамов в `backend/apps/hr/models.py` или `backend/apps/hr/enums.py`.

В CELERY_BEAT_SCHEDULE добавить:
```python
'hr-check-expirations': {
    'task': 'hr.tasks.hr_check_expirations',
    'schedule': crontab(hour=6, minute=0),
}
```

Написать тесты в `backend/apps/hr/tests.py`.

---

### BE-5.12 — Модель CreditModel (5h)
**Статус:** ❌ не сделано  
**Ветка:** `feature/TASK-5.12-credit-model`  
**Файлы:**
- `backend/apps/finances/models.py` — добавить модель
- `backend/apps/finances/migrations/` — создать миграцию
- `backend/apps/finances/admin.py` — зарегистрировать
- `backend/apps/finances/tests.py` — тесты

**Что сделать:**
Модель `CreditModel`:
```python
class CreditModel(models.Model):
    class Scenario(models.TextChoices):
        BASE = 'base', 'Базовый'
        STRESS = 'stress', 'Стресс'
        OPTIMISTIC = 'optimistic', 'Оптимистичный'

    name = models.CharField(max_length=255)
    scenario = models.CharField(max_length=20, choices=Scenario.choices, default=Scenario.BASE)
    period_start = models.DateField()
    period_end = models.DateField()
    # Прогнозный ОПиУ и CF в JSONField
    projected_income = models.JSONField(default=dict)   # {month: amount}
    projected_expenses = models.JSONField(default=dict)
    projected_cashflow = models.JSONField(default=dict)
    # Кредитные метрики
    loan_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    loan_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # %
    dscr = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    free_cashflow = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    risk_level = models.CharField(max_length=20, default='medium')  # low/medium/high
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_dscr(self):
        """DSCR = Net Operating Income / Total Debt Service"""
        ...
```

Написать тесты: создание, calculate_dscr, сценарии.

---

### BE-5.13 — ExchangeRate + Celery загрузка НБ РК (5h)
**Статус:** ❌ не сделано  
**Ветка:** `feature/TASK-5.13-exchange-rate`  
**Файлы:**
- `backend/apps/finances/models.py` — модель ExchangeRate
- `backend/apps/finances/migrations/`
- `backend/apps/finances/services/nbrk.py` — сервис парсинга
- `backend/apps/finances/tasks.py` — создать если нет
- `backend/project/settings.py` — Celery beat schedule
- `backend/apps/finances/tests.py` — тесты

**Что сделать:**

Модель:
```python
class ExchangeRate(models.Model):
    currency = models.CharField(max_length=3)  # USD, EUR, RUB, CNY
    date = models.DateField()
    rate = models.DecimalField(max_digits=20, decimal_places=6)
    source = models.CharField(max_length=50, default='nbrk')

    class Meta:
        unique_together = ('currency', 'date')

    @classmethod
    def convert(cls, amount, from_currency, to_currency='KZT', date=None):
        """Конвертация суммы через курс НБ РК"""
        ...
```

Сервис `nbrk.py`:
```python
def fetch_nbrk_rates(date=None):
    """Парсит XML с https://nationalbank.kz/rss/get_rates.cfm?fdate=DD.MM.YYYY"""
    import requests, xml.etree.ElementTree as ET
    ...
```

Celery task `fetch_exchange_rates` — ежедневно в 14:00.

Написать тесты с mock для HTTP запроса.

---

### BE-5.14 — Отправка счетов email + мессенджеры (6h)
**Статус:** ❌ не сделано  
**Ветка:** `feature/TASK-5.14-invoice-delivery`  
**Файлы:**
- `backend/apps/finances/services/` — создать `notifications.py`
- `backend/apps/finances/views.py` — обновить `invoice_send` view
- `backend/templates/finances/email/invoice.html` — email-шаблон
- `backend/apps/finances/tests.py` — тесты

**Что сделать:**

Существующий view `invoice_send` уже есть в `views.py` — он принимает `sent_via` (email/whatsapp/telegram/manual).

Доработать:
1. `send_invoice_via_email(invoice)` — отправить PDF (или HTML) через Django email backend. Обновить `invoice.sent_via = 'email'`, `invoice.sent_at = now()`, `invoice.status = 'sent'`.
2. `send_invoice_via_messenger(invoice, channel)` — заглушка (log + статус 'sent').
3. Tracking-endpoint для отметки `status='viewed'` (уже может быть — проверить `invoice_mark_viewed`).
4. Email-шаблон `email/invoice.html` — простой HTML с данными счёта.

Смотреть существующий код: `backend/apps/finances/views.py` функция `invoice_send`.

Тесты: mock Django email backend, проверить статусы.

---

### FE-5.4 — Шаблоны бюджетирования (8h)
**Статус:** ❌ не сделано  
**Ветка:** `feature/FE-5.4-budget-templates`  
**Файлы:**
- `backend/templates/site/finances/budget/budget_list.html` — уже есть, переверстать
- `backend/templates/site/finances/budget/budget_detail.html` — уже есть, доработать
- `backend/templates/site/finances/budget/budget_item_form.html` — уже есть, доработать
- `backend/static/site/js/apps/budget.js` — создать
- `backend/static/site/css/apps/finances.scss` — добавить стили (если нужно)

**Что сделать:**

Смотреть существующие шаблоны бюджета (`budget_list.html`, `budget_detail.html`) — они уже созданы в develop, но нужно привести к стилю `fin-*` (как в `payment_calendar.html`, `invoice_list.html`).

`budget_list.html`:
- Таблица статей бюджета по категориям
- Колонки: Категория / План / Факт / Прогноз / % освоения (прогресс-бар) / Отклонение (badge: зелёный/красный)
- Фильтр по периоду
- Кнопка «Создать статью» (только CFO — проверять `{% if user.role == 'CFO' %}`)
- Сигналы перерасхода (badge `is-danger` если факт > план)

`budget_detail.html`:
- Детализация статьи: название, категория, план/факт/прогноз
- Таблица позиций (BudgetItem)
- Кнопки редактировать/удалить (только CFO)

`budget_item_form.html`:
- Форма создания/редактирования статьи бюджета

`budget.js`:
- Динамический расчёт % освоения при вводе
- Подсветка строк с перерасходом

Смотреть стиль из `finances.scss` (классы `fin-*`) и `invoice_list.html` как образец верстки.

---

### FE-5.5 — Шаблоны ОПиУ + ДДС + кредитная модель (8h)
**Статус:** ❌ не сделано (зависит от BE-5.12 для кредитной модели)  
**Ветка:** `feature/FE-5.5-opiu-cashflow-credit`  
**Файлы:**
- `backend/templates/site/finances/opiu.html` — создать
- `backend/templates/site/finances/cashflow.html` — создать
- `backend/templates/site/finances/credit_model.html` — создать
- `backend/apps/finances/views.py` — добавить views для этих страниц
- `backend/apps/finances/urls.py` — добавить URLs

**Что сделать:**

`opiu.html` — Отчёт о прибылях и убытках:
- Таблица показателей: Revenue / EBITDA / Operating Profit / Net Profit / Рентабельность
- Колонки: Показатель / План / Факт / Отклонение / % отклонения
- Источник: модель `FinancialStatement` (уже есть в `finances/models.py`)
- View: `financial_statement` — GET список за выбранный период

`cashflow.html` — Реестр ДДС (движение денежных средств):
- Таблица операций: дата / контрагент / сумма / тип (приход/расход) / статья / onec_id
- Фильтры: период, тип, контрагент
- Источник: модель `CashFlowRecord` (уже есть)
- View: `cashflow_register` — GET с фильтрами

`credit_model.html` — Кредитная модель (только CFO):
- Форма создания сценария: название, тип (base/stress/optimistic), параметры кредита
- Таблица результатов: DSCR, free cashflow, risk_level
- View: `credit_model_list` + `credit_model_create`

Добавить в `urls.py`:
```python
path('opiu/', views.financial_statement, name='opiu'),
path('cashflow/', views.cashflow_register, name='cashflow'),
path('credit-model/', views.credit_model_list, name='credit_model_list'),
path('credit-model/create/', views.credit_model_create, name='credit_model_create'),
```

Добавить пункты в меню (`role_permissions.py`) для CFO/Owner/ChiefAccountant.

---

### COLLAB-3 — Стыковка Финансы Core (8h)
**Статус:** ❌ не сделано (после FE-5.4, FE-5.5, BE-5.14)  
**Что сделать:**
- Проверить все финансовые экраны на реальном контексте
- Smoke-test: реестр → календарь → счёт → бюджет → ОПиУ → ДДС
- Проверить разграничение по ролям: CFO видит всё + CRUD бюджета; ChiefAccountant — read-only; Owner — всё
- Исправить расхождения между BE-контекстом и FE-шаблонами

---

## Порядок выполнения

```
BE-2.fix   (1h)  → сразу, независимо
BE-2.21    (3h)  → сразу, независимо
BE-5.13    (5h)  → сразу, независимо
BE-5.12    (5h)  → сразу, независимо
BE-5.14    (6h)  → после проверки invoice_send в views.py
FE-5.4     (8h)  → сразу, BE-5.11 уже в develop
FE-5.5     (8h)  → BE-5.9/5.10 уже в develop; BE-5.12 нужен для credit_model
COLLAB-3   (8h)  → после FE-5.4, FE-5.5, BE-5.14
```

---

## Полезные файлы для изучения

- `backend/apps/finances/models.py` — все финансовые модели
- `backend/apps/finances/views.py` — существующие views
- `backend/apps/finances/urls.py` — существующие URLs
- `backend/apps/finances/tests.py` — примеры тестов
- `backend/apps/account/role_permissions.py` — роли и меню
- `backend/templates/site/finances/payment_calendar.html` — пример стиля `fin-*`
- `backend/templates/site/finances/invoice_list.html` — пример стиля `fin-*`
- `backend/static/site/css/apps/finances.scss` — финансовые стили

---

## Правила

1. **Каждая задача — отдельная ветка** от `sprint` (см. названия веток выше)
2. **Тесты обязательны** для каждой BE-задачи
3. **Стиль шаблонов** — `fin-*` CSS классы, как в `invoice_list.html`
4. **Коммит-сообщения** — `BE-5.12: CreditModel + DSCR` (ID задачи + краткое описание)
5. После каждой задачи — **PR в ветку `sprint`**, не в `develop`
