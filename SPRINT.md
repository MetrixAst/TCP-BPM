# TRC BPM — Sprint 4 (Phase 7 — Финализация → 100%)

**Ветка:** `sprint`  
**Цель:** REST API, JWT, Swagger, Docker prod, CI/CD, Audit, UAT → **~85% → ~100%**

---

## Что уже сделано (не трогать)

### Phase 5 ✅ — Финансы Core
- Модели, views, шаблоны: реестр, календарь, счета, бюджет, ОПиУ, ДДС, CreditModel, ExchangeRate
- BE-5.14: email-отправка счетов
- BE-2.21: Celery hr_check_expirations
- BE-2.fix: companies.html + positions.html

### Phase 6 ✅ — Дашборды
- BE-6.1–6.9: KPI, CF charts, drill-down, rent analytics, forecast, scenarios, Excel, filters, multi-currency
- FE-6.1–6.5 + COLLAB-4 (#84–#89): dashboard.html, Chart.js, rent_analytics, forecast, scenarios, finance_filters, role guards, mobile @media

### Существующая инфраструктура
- `docker-compose.yml` — db, redis, web (daphne), celery_worker, celery_beat (проверить наличие)
- `backend/project/settings.py` — JWT закомментирован: `# 'rest_framework_simplejwt.authentication.JWTAuthentication'`
- `drf-spectacular` — уже в requirements/venv, но `/api/docs/` может быть не подключён
- Serializers уже есть: `onec/serializers.py`, `hr/serializers.py`, `finances/serializers.py`, `tenants/serializers.py`
- 1С API: `/onec/api/counterparties/`, `/onec/api/invoices/` (Phase 4)
- Тесты finances: ~328+ зелёных

### Стек
- Django 4.2 + DRF + Celery + PostgreSQL + Redis + Daphne + Nginx (prod)
- Frontend: Django Templates SSR + Bootstrap 5 + Vanilla JS + Chart.js

---

## Задачи Спринта 4

### Порядок выполнения
```
BE-7.1 — первый (блокирует 7.2, 7.3, 7.4, 7.5, 7.7)
BE-7.2 + BE-7.3 — параллельно после 7.1
BE-7.7 + BE-7.4 — параллельно после 7.1
BE-7.5 — после 7.1
BE-7.6 — после 7.4 + 7.5
COLLAB-1, COLLAB-2 — параллельно (если не сделаны)
COLLAB-5 — последний (UAT на staging)
```

---

### BE-7.1 — Единое REST API DRF (8h)
**Статус:** ❌  
**Ветка:** `feature/TASK-7.1-rest-api`  
**Файлы:**
- `backend/apps/tasks/serializers.py` — создать/расширить
- `backend/apps/hr/serializers.py` — расширить
- `backend/apps/finances/serializers.py` — расширить
- `backend/project/urls.py` — роутер `/api/v1/`

**Что сделать:**

Создать единый роутер в `project/urls.py`:
```python
from rest_framework.routers import DefaultRouter
from apps.tasks.api import TaskViewSet
from apps.hr.api import EmployeeViewSet, DepartmentViewSet, CompanyViewSet
from apps.finances.api import (
    TenantPaymentRegistryViewSet,
    PaymentCalendarEntryViewSet,
    GeneratedInvoiceViewSet,
    BudgetItemViewSet,
)

router = DefaultRouter()
router.register('tasks', TaskViewSet)
router.register('hr/employees', EmployeeViewSet)
router.register('hr/departments', DepartmentViewSet)
router.register('hr/companies', CompanyViewSet)
router.register('finances/payments', TenantPaymentRegistryViewSet)
router.register('finances/calendar', PaymentCalendarEntryViewSet)
router.register('finances/invoices', GeneratedInvoiceViewSet)
router.register('finances/budget', BudgetItemViewSet)

urlpatterns += [
    path('api/v1/', include(router.urls)),
]
```

ViewSets — ReadOnly или CRUD по логике модуля:
- Tasks — CRUD + workflow actions
- HR — ReadOnly для Staff, CRUD для HR/Admin
- Finances — ReadOnly для реестра/календаря, CRUD для счетов/бюджета (CFO)

Общие настройки DRF в `settings.py`:
```python
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

Тесты: `APITestCase` для каждого ViewSet — list, retrieve, permissions (401 без auth, 403 без прав).

---

### BE-7.2 — JWT аутентификация (3h)
**Статус:** ❌ (зависит от BE-7.1)  
**Ветка:** `feature/TASK-7.2-jwt-auth`  
**Файлы:**
- `backend/requirements.txt` — `djangorestframework-simplejwt`
- `backend/project/settings.py`
- `backend/project/urls.py`

**Что сделать:**
```python
# settings.py
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
    'ROTATE_REFRESH_TOKENS': True,
}

REST_FRAMEWORK = {
    ...
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

# urls.py
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
urlpatterns += [
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
```

Тесты: POST `/api/token/` с credentials → 200 + access/refresh; POST `/api/token/refresh/` → новый access.

---

### BE-7.3 — Swagger / OpenAPI (3h)
**Статус:** ❌ (зависит от BE-7.1)  
**Ветка:** `feature/TASK-7.3-swagger`  
**Файлы:**
- `backend/project/settings.py`
- `backend/project/urls.py`

**drf-spectacular уже установлен** — нужно подключить:
```python
# settings.py
INSTALLED_APPS += ['drf_spectacular']
REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS'] = 'drf_spectacular.openapi.AutoSchema'

SPECTACULAR_SETTINGS = {
    'TITLE': 'TRC BPM API',
    'DESCRIPTION': 'MetriX BPM — Tasks, HR, Finances, 1C Integration',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# urls.py
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
urlpatterns += [
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

Тесты: GET `/api/schema/` → 200 JSON; GET `/api/docs/` → 200 HTML.

---

### BE-7.4 — Тесты coverage > 70% (10h)
**Статус:** ❌ (зависит от BE-7.1)  
**Ветка:** `feature/TASK-7.4-tests`  
**Файлы:** `backend/apps/*/tests.py`, `backend/pytest.ini` или `setup.cfg`

**Что сделать:**
1. Установить `pytest`, `pytest-django`, `pytest-cov`
2. Добавить `pytest.ini`:
```ini
[pytest]
DJANGO_SETTINGS_MODULE = project.settings
python_files = tests.py test_*.py
addopts = --cov=apps --cov-report=term-missing --cov-fail-under=70
```
3. Дописать тесты для модулей с низким покрытием:
   - `apps/tasks/tests.py` — workflow transitions
   - `apps/hr/tests.py` — leave workflow, attendance
   - `apps/onec/tests.py` — counterparty sync mock
   - `apps/finances/tests.py` — уже ~328, проверить gaps
4. Запуск: `pytest --cov=apps --cov-report=html`

---

### BE-7.5 — Docker production deployment (5h)
**Статус:** ❌ (зависит от BE-7.1)  
**Ветка:** `feature/TASK-7.5-docker-deploy`  
**Файлы:**
- `docker-compose.yml` — доработать prod-профиль
- `docker-compose.prod.yml` — создать (или `docker-compose.override.yml`)
- `backend/Dockerfile` — проверить/создать
- `nginx/nginx.conf` — создать
- `backend/.env.example` — обновить prod-переменные

**Что сделать:**

`docker-compose.prod.yml`:
```yaml
services:
  web:
    command: daphne project.asgi:application -b 0.0.0.0 -p 8000
    environment:
      - DEBUG=False
    restart: always
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
      - static_volume:/static
      - media_volume:/media
    depends_on:
      - web
  celery_worker:
    restart: always
  celery_beat:
    restart: always
```

`nginx/nginx.conf` — proxy_pass на web:8000, static/media volumes.

`backend/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /home/app/web
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["daphne", "project.asgi:application", "-b", "0.0.0.0", "-p", "8000"]
```

Обновить `.env.example`:
```
DEBUG=False
ALLOWED_HOSTS=your-domain.com
SECRET_KEY=change-me-in-production
```

---

### BE-7.6 — CI/CD GitHub Actions (4h)
**Статус:** ❌ (зависит от BE-7.4 + BE-7.5)  
**Ветка:** `feature/TASK-7.6-cicd`  
**Файлы:** `.github/workflows/ci.yml`

**Что сделать:**
```yaml
name: CI

on:
  push:
    branches: [develop, sprint, main]
  pull_request:
    branches: [develop, main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_trc_bpm
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports: ['5432:5432']
      redis:
        image: redis:7
        ports: ['6379:6379']

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-django pytest-cov
      - name: Run tests
        env:
          SECRET_KEY: test-secret-key
          POSTGRES_DB: test_trc_bpm
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_HOST: localhost
          DEBUG: 'True'
        run: |
          cd backend
          python manage.py migrate --noinput
          pytest --cov=apps --cov-fail-under=70

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t trc-bpm ./backend
```

---

### BE-7.7 — Audit trail (8h)
**Статус:** ❌ (зависит от BE-7.1)  
**Ветка:** `feature/TASK-7.7-audit-trail`  
**Файлы:**
- `backend/apps/audit/` — новое приложение
- `backend/project/settings.py` — INSTALLED_APPS

**Что сделать:**

Создать приложение `audit`:
```python
# apps/audit/models.py
class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'create', 'Создание'
        UPDATE = 'update', 'Изменение'
        DELETE = 'delete', 'Удаление'
        LOGIN  = 'login',  'Вход'
        EXPORT = 'export', 'Экспорт'

    user       = models.ForeignKey('account.User', on_delete=SET_NULL, null=True)
    action     = models.CharField(max_length=20, choices=Action.choices)
    object_type = models.CharField(max_length=100)  # 'GeneratedInvoice', 'Employee', etc.
    object_id  = models.CharField(max_length=100)
    object_repr = models.CharField(max_length=255, blank=True)
    changes    = models.JSONField(default=dict)  # {field: [old, new]}
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['object_type', 'object_id'])]
```

Middleware `AuditMiddleware` — логирует IP и UA в thread-local.

Signals для критичных моделей:
- `GeneratedInvoice` — create/update/delete/status change
- `BudgetItem` — create/update
- `Employee` — create/update/delete
- `LeaveRequest` — approve/reject

View `/audit/log/` — только Administrator, таблица с фильтрами (user, action, date range).

Тесты: signal создаёт AuditLog при save/delete, view 403 для Staff, 200 для Admin.

---

### COLLAB-1 — Стыковка HR-блока (6h)
**Статус:** ❓ проверить — возможно не формально закрыта  
**Ветка:** `feature/COLLAB-1-hr-integration`

Smoke-test:
- Создать сотрудника → документ → допуск → сертификация → отпуск → фотофиксация
- Фильтры, пагинация, Excel-export работают
- Исправить расхождения FE/BE

---

### COLLAB-2 — Стыковка 1С-блока (4h)
**Статус:** ❓ проверить  
**Ветка:** `feature/COLLAB-2-onec-integration`

Smoke-test:
- Counterparty list/detail с Select2
- Invoice create с динамическими позициями
- Обработка ошибки при недоступности 1С

---

### COLLAB-5 — UAT финальная приёмка (12h)
**Статус:** ❌ (после BE-7.5, BE-7.6, все COLLAB)  
**Ветка:** `feature/COLLAB-5-uat`

**Сценарии по ролям (на staging Docker):**

| Роль | Сценарий |
|------|----------|
| HR | Создать сотрудника → документ → допуск → сертификация → отпуск → checkin |
| Бухгалтер | Реестр оплат → выставить счёт → отправить email → отметить оплаченным |
| CFO | Dashboard → drill-down → бюджет CRUD → сценарии → прогноз CF |
| Owner | Executive dashboard → аналитика аренды → Excel export |
| Admin | Audit log → все модули доступны |

**Критерии приёмки:**
- [ ] Все экраны открываются без 500
- [ ] Права по ролям работают (403 где нужно)
- [ ] API `/api/v1/` отвечает с JWT
- [ ] Swagger `/api/docs/` доступен
- [ ] CI зелёный на push в develop
- [ ] Docker prod поднимается одной командой

---

## Backlog UI/UX (параллельно, не блокирует)

| # | Правка | Приоритет |
|---|--------|-----------|
| 1 | Favicon MetriX | Быстро |
| 2 | Логотип: X зелёная | Быстро |
| 3 | Единая дизайн-система | Средне |
| 4 | Меню задач — убрать «я» | Быстро |
| 5–7 | HR-календарь: иконки, рабочие дни, типы событий | Средне |
| 8–9 | Контрагенты + реестр — общие стили | Средне |
| 10 | Сотрудник → оргструктура после создания | Средне |
| 11 | Кнопка «Удалить» у сотрудника | Средне |

---

## Итого Спринт 4

| Задача | Ветка | Оценка |
|--------|-------|--------|
| BE-7.1 REST API | feature/TASK-7.1-rest-api | 8h |
| BE-7.2 JWT | feature/TASK-7.2-jwt-auth | 3h |
| BE-7.3 Swagger | feature/TASK-7.3-swagger | 3h |
| BE-7.4 Tests >70% | feature/TASK-7.4-tests | 10h |
| BE-7.5 Docker prod | feature/TASK-7.5-docker-deploy | 5h |
| BE-7.6 CI/CD | feature/TASK-7.6-cicd | 4h |
| BE-7.7 Audit trail | feature/TASK-7.7-audit-trail | 8h |
| COLLAB-1 HR | feature/COLLAB-1-hr-integration | 6h |
| COLLAB-2 1С | feature/COLLAB-2-onec-integration | 4h |
| COLLAB-5 UAT | feature/COLLAB-5-uat | 12h |
| **ИТОГО** | | **~63h** |

**После Спринта 4 → ~100%**

---

## Правила

1. Ветки от `sprint`, PR в `sprint`
2. После завершения Sprint 4 — **merge `sprint` → `develop`**
3. Коммиты: `BE-7.1: REST API /api/v1/ для tasks/hr/finances`
4. Тесты обязательны для каждой BE-задачи

---

## Прогресс проекта

| Фаза | Статус |
|------|--------|
| Phase 1 — Задачи | ✅ ~90% |
| Phase 2 — HR | ✅ ~95% |
| Phase 3 — Enbek.kz | ⏸ заморожена |
| Phase 4 — 1С | ✅ 100% |
| Phase 5 — Финансы Core | ✅ 100% |
| Phase 6 — Дашборды | ✅ 100% |
| Phase 7 — Финализация | ❌ 0% |
| **ИТОГО** | **~85%** |
