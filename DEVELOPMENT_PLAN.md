# План разработки TRC BPM

## Техническое задание

Разработка BPM системы с модулями HR, интеграции с Enbek.kz, 1С и управления задачами.

---

## Архитектура

- **Backend:** Django 4.2 LTS + DRF + Celery
- **БД:** PostgreSQL 15
- **Кэш/Брокер:** Redis 7
- **Фоновые задачи:** Celery Worker + Celery Beat
- **Веб-сервер:** Nginx + Daphne
- **Контейнеризация:** Docker + Docker Compose

---

## Фаза 1: Модуль задач (Неделя 1-2)

Готовность: ~50-80%. Нужна доработка статусов, приоритетов и workflow.

### 1.1 Обновить статусы задач
- **Файл:** `backend/apps/tasks/enums.py`
- Заменить текущие статусы (`TO_DO`, `DOING`, `DONE`, `ARCHIVE`) на:
  - `CREATED` — Создана
  - `ACCEPTED` — Принята
  - `REJECTED` — Отклонена
  - `REVISION` — На доработке
  - `COMPLETED` — Завершена
- Обновить методы `get_full()`, `get_actions()`, `get_notification_text()`

### 1.2 Добавить приоритет и соисполнителя
- **Файл:** `backend/apps/tasks/models.py`
- Добавить поле `priority` (choices: `low`, `medium`, `high`, `critical`)
- Добавить `co_executors = ManyToManyField(UserAccount)` — соисполнители
- **Файл:** `backend/apps/tasks/forms.py` — добавить новые поля в форму

### 1.3 Реализовать workflow по ТЗ
- **Файл:** `backend/apps/tasks/models.py` → метод `set_action()`
- Логика переходов:
  - Автор создаёт задачу → статус `CREATED`
  - Исполнитель принимает → `ACCEPTED` или отклоняет → `REJECTED`
  - Исполнитель завершает → `COMPLETED`
  - Автор возвращает на доработку → `REVISION`
- Проверка прав: кто может выполнять какое действие

### 1.4 Миграции и тесты
- `python manage.py makemigrations tasks`
- Data migration для существующих задач
- Обновить шаблоны в `backend/templates/site/tasks/`

---

## Фаза 2: HR модуль — сотрудники и оргструктура (Неделя 2-4)

Готовность: ~30-50%. Нужна оргструктура, расширение модели сотрудника.

### 2.1 Расширить оргструктуру
- **Файл:** `backend/apps/hr/models.py`
- Добавить модели:
  - `Company` — компания (название, БИН, адрес)
  - `Position` — должность (название, FK → Department, описание)
- Или добавить `level_type` в существующую модель `Department` (MPTT) для разделения: company/department/division

### 2.2 Расширить модель сотрудника
- **Файл:** `backend/apps/account/models.py` → модель `Employee`
- Добавить поля:
  - `iin` — ИИН (CharField, max_length=12, unique)
  - `status` — choices: `active`, `dismissed`, `vacation`, `sick_leave`
  - `hire_date` — DateField (дата приёма)
  - `supervisor` — ForeignKey на Employee (руководитель)
  - `phone` — CharField (телефон)
  - `personal_email` — EmailField
  - `position` — ForeignKey на Position

### 2.3 Обновить views и формы
- **Файлы:** `backend/apps/hr/views.py`, `backend/apps/hr/forms.py`
- Обновить `EmployeeForm`, `EmployeeCreationForm`
- Добавить фильтры по статусу, должности, департаменту
- Обновить шаблоны: `backend/templates/site/hr/`

### 2.4 Заменить фейковый OrgChart
- **Файл:** `backend/apps/hr/utils.py` → класс `OrgChart`
- Вместо random-генерации — реальные данные из `Department` (MPTT) + `Employee`

### 2.5 Миграции
- Data migration для переноса `job_title` → `Position`

---

## Фаза 3: Интеграция с Enbek.kz (Неделя 4-6)

Готовность: 0%. Полностью новый модуль.

### 3.1 Исследование API Enbek.kz
- Получить документацию API и ключи доступа
- Определить endpoints: отпуска, больничные, трудовые договоры
- Формат авторизации (OAuth, API key, ЭЦП)

### 3.2 Создать клиент Enbek.kz
- **Новый файл:** `backend/apps/hr/enbek_client.py`
- Класс `EnbekClient` — авторизация, получение данных
- По аналогии с `backend/apps/onec/client_1c/client.py`

### 3.3 Создать модели синхронизации
- **Файл:** `backend/apps/hr/models.py`
- `Vacation` — отпуска (сотрудник, тип, дата начала/конца, статус, enbek_id)
- `SickLeave` — больничные (сотрудник, дата начала/конца, документ, enbek_id)
- `EmploymentContract` — трудовые договоры (сотрудник, номер, дата, тип, статус, enbek_id)

### 3.4 Сервис синхронизации
- **Новый файл:** `backend/apps/hr/services.py`
- Класс `EnbekSyncService` — логика upsert по `enbek_id`
- Источник правды: Enbek.kz (при конфликте данные Enbek перезаписывают)

### 3.5 Celery periodic task
- **Новый файл:** `backend/apps/hr/tasks.py`
- Task `sync_enbek_data` — вызывает `EnbekSyncService`
- Добавить в `celery beat schedule` в `settings.py` — каждые 6 часов

### 3.6 Admin + views
- Регистрация моделей в `backend/apps/hr/admin.py`
- Views для просмотра отпусков/больничных/договоров
- Обновить HR-меню в `backend/apps/account/role_permissions.py`

---

## Фаза 4: Интеграция с 1С в Django (Неделя 5-7)

Готовность: ~35-40%. Клиент перенесён, нужны модели и views.

### 4.1 Модель контрагента
- **Файл:** `backend/apps/onec/models.py`
- Новая модель `Counterparty`:
  - `id_1c` — ID из 1С (unique)
  - `full_name` — полное наименование
  - `bin` — БИН (unique)
  - `iin` — ИИН
  - `address`, `phone`, `email`
  - `bank_accounts` — JSONField
  - `contracts` — JSONField
  - `synced_at` — DateTimeField

### 4.2 Расширить модель Invoice
- **Файл:** `backend/apps/onec/models.py`
- Добавить в `Invoice`: `counterparty` (FK), `number`, `status`, `comment`
- Новая модель `InvoiceItem` — позиции счёта (название, количество, цена, сумма)

### 4.3 Создать URLs и Views
- **Новый файл:** `backend/apps/onec/urls.py`
- Views:
  - Список контрагентов (с Select2 поиском)
  - Карточка контрагента
  - Создание счёта (выбор контрагента → позиции → отправка в 1С)
- Зарегистрировать в `backend/project/urls.py`

### 4.4 REST API endpoints (DRF)
- **Файл:** `backend/apps/onec/serializers.py` — расширить
- Serializers для `Counterparty`, `Invoice`, `InvoiceItem`
- ViewSets или APIViews для CRUD

### 4.5 Синхронизация контрагентов
- Celery task для периодического pull из 1С
- Использовать `client_1c.get_counterparties()` → upsert в модель `Counterparty`

---

## Фаза 5: Финализация и интеграция (Неделя 7-9)

### 5.1 REST API для всех модулей
- Добавить DRF serializers + viewsets для HR, Tasks
- Настроить JWT аутентификацию (раскомментировать в settings.py)
- Swagger/OpenAPI документация

### 5.2 Уведомления
- Расширить модель `Notification` для новых событий:
  - Синхронизация Enbek.kz завершена
  - Новый счёт из 1С
  - Изменение статуса задачи (проверить workflow)

### 5.3 Docker и деплой
- Обновить `docker-compose.yml` при необходимости
- Environment variables для production
- CI/CD через GitHub Actions (опционально)

### 5.4 Тестирование
- Unit-тесты для сервисов (Enbek, 1С, Tasks workflow)
- Integration-тесты для API
- Тест синхронизации (mock Enbek/1С API)

---

## Таймлайн

| Фаза | Срок | Зависимости | Исполнитель |
|---|---|---|---|
| Фаза 1: Задачи | Неделя 1-2 | Нет | — |
| Фаза 2: HR + Оргструктура | Неделя 2-4 | Нет | — |
| Фаза 3: Enbek.kz | Неделя 4-6 | Фаза 2 (модель Employee) | — |
| Фаза 4: 1С в Django | Неделя 5-7 | Нет (параллельно с Фазой 3) | — |
| Фаза 5: Финализация | Неделя 7-9 | Все предыдущие | — |

Фазы 3 и 4 можно вести параллельно — общий срок ~6-7 недель при двух разработчиках.

---

## Git Workflow

```
main              — продакшн, защищена (требует PR + approve)
develop           — интеграционная ветка
feature/task-*    — ветки задач (от develop, PR в develop)
```

Каждый разработчик:
1. Создаёт ветку от `develop`: `git checkout -b feature/task-statuses develop`
2. Делает работу, коммитит
3. Пушит: `git push -u origin feature/task-statuses`
4. Создаёт Pull Request в `develop`
5. После ревью и одобрения — merge
