# metriX BPM (TRC-BPM)

Корпоративная BPM-система: управление задачами, HR и оргструктурой, финансы, документооборот,
портал арендаторов и интеграции с 1С и Enbek.

- **Backend:** Django 4.2 + Django REST Framework, PostgreSQL, Celery (Redis), Daphne/Gunicorn.
- **Frontend (server-side):** Django-шаблоны + собственная дизайн-система (SCSS/CSS, ванильный JS).
- **Frontend (отдельный):** Next.js-прототип в `frontend/` (не основной UI, см. ниже).
- **Локализация:** RU / KK / EN (собственный механизм i18n, переключение через `?lang=`).

---

## Содержание

1. [Архитектура](#архитектура)
2. [Стек и зависимости](#стек-и-зависимости)
3. [Структура репозитория](#структура-репозитория)
4. [Django-приложения (apps)](#django-приложения-apps)
5. [Быстрый старт (Docker)](#быстрый-старт-docker)
6. [Локальный запуск (без Docker)](#локальный-запуск-без-docker)
7. [Переменные окружения](#переменные-окружения)
8. [Частые команды](#частые-команды)
9. [Роли и права доступа](#роли-и-права-доступа)
10. [REST API и аутентификация](#rest-api-и-аутентификация)
11. [Интеграции (1С, Enbek)](#интеграции-1с-enbek)
12. [Фоновые задачи (Celery)](#фоновые-задачи-celery)
13. [Локализация (i18n)](#локализация-i18n)
14. [Фронтенд и стили](#фронтенд-и-стили)
15. [Тесты](#тесты)
16. [Деплой](#деплой)

---

## Архитектура

```
            ┌─────────────┐      ┌──────────────┐
  Браузер → │   nginx     │ ───→ │  web (Daphne)│ ── Django (ASGI)
            └─────────────┘      └──────┬───────┘
                                        │
                  ┌─────────────────────┼─────────────────────┐
                  │                      │                     │
            ┌─────▼─────┐         ┌──────▼──────┐       ┌──────▼──────┐
            │ PostgreSQL│         │   Redis     │       │  Внешние:   │
            └───────────┘         │ (брокер     │       │  1С, Enbek  │
                                  │  Celery)    │       └─────────────┘
                                  └──────┬──────┘
                          ┌──────────────┴──────────────┐
                    ┌─────▼──────┐                ┌──────▼──────┐
                    │celery_worker│               │ celery_beat │
                    └─────────────┘               └─────────────┘
```

UI рендерится Django-шаблонами (`backend/templates/`). REST API (`/api/v1/`) обслуживает
мобильные/внешние клиенты и часть AJAX. Тяжёлые и периодические операции (синхронизация с 1С,
Enbek, уведомления, проверки HR-сроков) уходят в Celery.

---

## Стек и зависимости

| Слой | Технологии |
|------|-----------|
| Язык / фреймворк | Python 3.11, Django 4.2.17 |
| API | Django REST Framework 3.15, SimpleJWT, drf-spectacular (OpenAPI) |
| БД | PostgreSQL 15 (по умолчанию SQLite в dev, если не задан Postgres) |
| Очереди | Celery 5.4 + Redis 7, django-celery-beat, django-celery-results |
| Деревья | django-mptt (оргструктура, отделы) |
| Сервер | Daphne (ASGI) / Gunicorn, nginx |
| Документы | openpyxl (Excel), xhtml2pdf (PDF) |
| Push | pyfcm (FCM) |
| Конфиг | python-decouple (`.env`) |

Полный список — `backend/requirements.txt`, dev-зависимости — `backend/requirements-dev.txt`.

---

## Структура репозитория

```
trc-bpm/
├── backend/                  # основной Django-проект
│   ├── apps/                 # бизнес-приложения (см. ниже)
│   ├── project/              # settings, urls, asgi/wsgi, celery, api_urls
│   ├── templates/site/       # серверные HTML-шаблоны
│   ├── static/site/          # CSS/SCSS, JS, изображения, шрифты
│   ├── media/                # загруженные файлы (runtime)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example          # шаблон переменных окружения
├── frontend/                 # Next.js прототип + дизайн-токены (вторичный)
├── nginx/                    # конфиг и Dockerfile nginx
├── docker-compose.yml        # dev/локальный стек
├── docker-compose.prod.yml   # production-стек
├── ТЗ.md / BRD.md / PLAN.md  # продуктовые требования и план
└── SPRINT.md                 # статус спринтов
```

---

## Django-приложения (apps)

Все приложения лежат в `backend/apps/` (добавлены в `sys.path`, поэтому импортируются по имени:
`from tasks.models import Task`).

| App | Назначение |
|-----|-----------|
| `account` | Пользователи (`UserAccount`), роли и права (`role_permissions.py`), оргструктура (D3/CSV), профиль, i18n-middleware, auth |
| `dashboard` | Главная страница «Добро пожаловать» (сводка задач/документов/уведомлений) |
| `tasks` | Менеджер задач: карточка задачи, workflow-статусы, канбан, чеклисты, позиции, комментарии |
| `hr` | Сотрудники, отделы, компании, должности, отпуска, командировки, кадровые документы, допуски, посещаемость, HR-календарь |
| `finances` | Финансовый дашборд, реестр оплат, календарь платежей, счета, ОПиУ, ДДС, бюджетирование, кредитная модель, аналитика аренды |
| `onec` | Интеграция с 1С, справочник контрагентов |
| `documents` | Документооборот (согласование, статусы) |
| `purchases` | Закупки и поставщики |
| `tenants` | Арендаторы / компании |
| `requistions` | Заявки портала арендатора |
| `reports` | Финансовые отчёты |
| `ecopark` | Модуль эксплуатации |
| `enbek` | Интеграция с гос-сервисом Enbek (отпуска/больничные/договоры) |
| `addits` | Комментарии (универсальные), кастомные страницы ошибок 403/404/500 |
| `audit` | Middleware аудита действий пользователей |

---

## Быстрый старт (Docker)

Требуется Docker + Docker Compose.

```bash
# 1. Подготовить .env
cp backend/.env.example backend/.env
# отредактировать SECRET_KEY, доступы к Postgres / 1С / Enbek

# 2. Поднять стек (web, db, redis, celery_worker, celery_beat, nginx)
docker compose up --build
```

Контейнер `web` при старте сам выполняет `collectstatic` и `migrate` (см. `docker-compose.yml`).

```bash
# 3. Создать суперпользователя
docker compose exec web python manage.py createsuperuser
```

Приложение: <http://localhost> (через nginx) или <http://localhost:8000> (напрямую web).
Swagger: <http://localhost/api/docs/>.

---

## Локальный запуск (без Docker)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # для dev можно не задавать Postgres — будет SQLite

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

> Без переменных `POSTGRES_*` проект использует SQLite (`db.sqlite3`).
> `SECRET_KEY` и `TZ` обязательны (в `.env`).

Для фоновых задач локально нужен Redis и два процесса:

```bash
celery -A project worker -l info
celery -A project beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Переменные окружения

Шаблон — `backend/.env.example`. Ключевые:

| Переменная | Назначение |
|-----------|-----------|
| `SECRET_KEY` | Django secret (обязательно) |
| `DEBUG` | `True`/`False` |
| `ALLOWED_HOSTS`, `TRUSTED_ORIGINS` | хосты и CSRF-origins (CSV) |
| `POSTGRES_ENGINE/DB/USER/PASSWORD/HOST/PORT` | БД (если не заданы — SQLite) |
| `CELERY_BROKER_URL` | Redis, напр. `redis://redis:6379/0` |
| `TZ` | таймзона, напр. `Asia/Almaty` (обязательно) |
| `ONE_C_BASE_URL`, `ONE_C_API_USER/PASSWORD`, `ONE_C_BASIC_AUTH_*` | доступ к 1С |
| `ONE_C_SYNC_ENABLED`, `ONE_C_SYNC_SINCE_DAYS` | управление синхронизацией 1С |
| `ENBEK_BASE_URL`, `ENBEK_USERNAME`, `ENBEK_PASSWORD` | доступ к Enbek |

---

## Частые команды

Выполнять из `backend/` (с активированным venv) или через `docker compose exec web …`.

```bash
python manage.py check                 # системные проверки
python manage.py migrate               # применить миграции
python manage.py makemigrations <app>  # создать миграции
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py test                  # все тесты
python manage.py test account.tests_sprint_fix_uat   # конкретный модуль
python manage.py sync_onec             # ручная синхронизация с 1С
```

Компиляция стилей (где есть `.scss`):

```bash
cd backend/static/site/css/apps
npx sass tasks.scss tasks.css --no-source-map
```

---

## Роли и права доступа

Модель прав — в `backend/apps/account/role_permissions.py`.

**Роли (`RoleEnums`):** `administrator`, `hr`, `staff`, `guest`, `tenant`, `owner`, `cfo`,
`chief_accountant`.

**Права (`PermissionEnums`):** `tasks`, `edit_task`, `documents`, `finances`, `hr`,
`finance_registers`, `requistions`, `reports` и др. Сопоставление роль→права задаётся в
`RolePermissions.permissions`.

Проверки:

- View-уровень: декоратор `@need_permission(PermissionEnums.TASKS)`.
- Шаблоны: фильтр `{{ user|has_permission:"finances" }}`.
- Меню сайдбара строится из `MenuItem(...)` по правам пользователя.

Портальные роли (`guest`, `tenant`) видят только портал заявок; внутренние роли
(`administrator`, `hr`, `staff`) получают уведомления по арендаторам.

---

## REST API и аутентификация

Роутинг API — `backend/project/api_urls.py` (DRF `DefaultRouter`), подключён под `/api/v1/`.

| Endpoint | Ресурс |
|----------|--------|
| `/api/v1/tasks/` | Задачи |
| `/api/v1/hr/employees/`, `/hr/departments/`, `/hr/companies/` | HR |
| `/api/v1/finances/payments/`, `/calendar/`, `/invoices/`, `/budget/` | Финансы |
| `/api/enbek/` | Интеграция Enbek |
| `/api/schema/` · `/api/docs/` | OpenAPI-схема и Swagger UI |

**Аутентификация (DRF):** JWT (SimpleJWT), Session, Basic.

```bash
# получить токены
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"***"}'

# использовать access-токен
curl http://localhost:8000/api/v1/tasks/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

JWT: access — 30 дней, refresh — 90 дней, ротация включена. Пагинация по умолчанию — 50 на
страницу; поддерживаются `django-filter`, поиск и сортировка.

---

## Интеграции (1С, Enbek)

**1С (`onec`):** синхронизация контрагентов и финансовых данных. Настройки — `ONE_C_*` в `.env`.
Ручной запуск: `python manage.py sync_onec`. Периодически — через Celery (`sync_counterparties_task`,
`sync_onec_all_task`, каждые 4 часа).

**Enbek (`enbek`):** загрузка отпусков, больничных и договоров. Настройки — `ENBEK_*`.
Периодически — `hr.tasks.sync_enbek_data` (каждые 6 часов).

---

## Фоновые задачи (Celery)

Брокер — Redis, бэкенд результатов — `django-db`. Расписание — `CELERY_BEAT_SCHEDULE` в
`settings.py`:

| Задача | Расписание | Назначение |
|--------|-----------|-----------|
| `sync_counterparties_task` | каждые 4 ч | контрагенты из 1С |
| `sync_onec_all_task` | каждые 4 ч | финансы из 1С |
| `hr.tasks.sync_enbek_data` | каждые 6 ч | данные из Enbek |
| `hr.tasks.hr_check_expirations` | ежедневно 06:00 | проверка сроков (допуски/документы) |

> Курсы валют НБ РК отключены — суммы хранятся и отображаются в ₸.

---

## Локализация (i18n)

Собственный механизм (не Django gettext):

- Словари: `backend/apps/account/locale/{ru,kk,en}.json`.
- API: `account/i18n.py` → `translate(lang, key, default)`.
- Шаблоны: тег `{% t 'tasks.status' 'Статус' %}` и `{% menu_t %}`.
- Язык определяется `account/language_middleware.LanguageMiddleware`; переключение — `?lang=en`.
- Языки по умолчанию: `ru` (основной), `kk`, `en`.

При добавлении строки — добавляйте ключ во все три JSON; в шаблоне всегда указывайте
fallback-текст вторым аргументом тега `t`.

---

## Фронтенд и стили

Основной UI — серверные шаблоны Django в `backend/templates/site/`. Стили — в
`backend/static/site/css/`:

- `design-system.css` — общие токены (`--bpm-*`) и базовые классы для всех модулей
  (подключён глобально в `base.html`).
- `apps/*.scss` → `apps/*.css` — модульные стили (tasks, finances, onec, hr и т.д.).
  Источник истины — `.scss`; после правок компилируйте в `.css` (`npx sass …`).
- `bpm-modal.css` / `bpm-modal.js` — глобальные модальные окна (замена браузерных alert/confirm).

Каталог `frontend/` — отдельный Next.js-прототип и дизайн-документация
(`COMPONENTS.md`, `DESIGN-TOKENS.md`); он **не** обслуживает основной интерфейс.

---

## Тесты

```bash
cd backend
python manage.py test                       # всё
python manage.py test tasks                  # один app
python manage.py test account.tests_sprint_fix_uat   # UAT-набор
```

Тесты используют Django test runner. UAT-сценарии спринта — в
`apps/account/tests_sprint_fix_uat.py`.

---

## Деплой

Production — overlay поверх базового compose (web через Daphne за nginx, отдельные
`celery_worker` и `celery_beat`, `restart: always`):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Чек-лист перед продом:

1. `DEBUG=False`, заданы `ALLOWED_HOSTS` и `TRUSTED_ORIGINS`.
2. Сгенерирован уникальный `SECRET_KEY`.
3. Настроен внешний PostgreSQL и Redis.
4. `python manage.py collectstatic --noinput` (выполняется автоматически в `web`).
5. `python manage.py migrate`.
6. Проверены доступы к 1С / Enbek.

---

## Дополнительные материалы

- `backend/I18N.md` — детали локализации.
- Swagger: `/api/docs/`.
