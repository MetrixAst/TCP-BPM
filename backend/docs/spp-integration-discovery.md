# Discovery интеграции Metrix SPP

## 1. Собранные данные

### 1.1 API-документация

- В проекте уже реализована интеграция с 1С (`apps/onec/client_1c/client.py`) по паттерну: BasicAuth + Bearer-токен (`X-Authorization`), REST/JSON, sync-token для инкрементальной загрузки.


### 1.2 Sandbox / тестовый доступ

| Параметр | Статус |
|---|---|
| Sandbox URL | Не получен |
| Тестовые учётные данные | Не получены |
| Whitelist IP для sandbox | Неизвестно — уточнить |
| Документация sandbox | Не получена |

**После получения:** добавить в `.env.example`:
```env
# Metrix СПП
SPP_BASE_URL=
SPP_SANDBOX_URL=
SPP_CLIENT_ID=
SPP_CLIENT_SECRET=
SPP_API_KEY=
SPP_TIMEOUT=30
SPP_SYNC_ENABLED=False
```

### 1.3 Механизм авторизации (Auth)

| Вариант | Вероятность | Основание |
|---|---|---|
| OAuth 2.0 (client_credentials) | Высокая | Современный стандарт для B2B |
| API Key в заголовке (`X-API-Key`) | Средняя | Простые корпоративные системы РК |
| BasicAuth + Bearer-токен (как 1С) | Средняя | Уже используется в проекте |
| MTLS (сертификаты) | Низкая | Характерно для государственных систем РК |

**Заготовка клиента**
```python
# backend/apps/spp/client.py
import requests
from django.conf import settings

class SPPClient:
    def __init__(self):
        self.base_url = settings.SPP_BASE_URL.rstrip('/')
        self.timeout = getattr(settings, 'SPP_TIMEOUT', 30)
        self._token = None
        self._session = requests.Session()

    def _authenticate(self):
        raise NotImplementedError("Auth mechanism")

    def get(self, endpoint: str, params: dict = None):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {'Authorization': f'Bearer {self._token}'}
        response = self._session.get(url, headers=headers,
                                     params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
```

### 1.4 Сетевые требования (Network)

| Параметр | Текущее состояние | Необходимо уточнить |
|---|---|---|
| Протокол | HTTPS | Стандарт |
| Порт | 443 | |
| IP Whitelist | Неизвестно | Нужен IP сервера MetrixAst для whitelist |
| VPN/закрытая сеть | | |
| Firewall-правила | Не настроены | Настроить после получения данных |
| Таймаут | 30 сек (по аналогии с eSigner) | Может потребоваться коррекция |

1. Запросить IP/подсети для whitelist
2. Добавить правило в nginx / Docker network
3. Проверить доступность: `curl -I https://spp.metrix.com.ai`

---

## 2. Mapping полей / сущностей


### 2.1 Сотрудник (Employee)

| TCP-BPM | Поле Django | SPP | Примечание |
|---|---|---|---|
| `Employee.iin` | `CharField(12)` | `iin` / `individualNumber` | |
| `Employee.user.first_name` | `CharField` | `firstName` | |
| `Employee.user.last_name` | `CharField` | `lastName` | |
| `Employee.hire_date` | `DateField` | `hireDate` | |
| `Employee.status` | `EmployeeStatusEnum` | `employmentStatus` | |
| `Employee.position.title` | `ForeignKey → Position` | `positionName` / `positionCode` | |
| `hr.Company.bin_number` | `CharField(12)` | `bin` / `companyBin` | БИН — ключ компании |

### 2.2 Табель посещаемости (AttendanceRecord)

| TCP-BPM | Поле Django | SPP (ожидаемое) | Примечание |
|---|---|---|---|
| `AttendanceRecord.timestamp` | `DateTimeField` | `checkTime` / `eventTime` | Часовой пояс: Asia/Almaty |
| `AttendanceRecord.event_type` | `CheckInEnum` | `eventType` | Маппинг: уточнить коды |
| `AttendanceRecord.employee` | FK → Employee | `iin` / `employeeId` | |
| — | — | `workHours` | СПП может считать часы — хранить в будущей модели |
| — | — | `overtimeHours` | Переработки — нет в текущей модели |

**Маппинг типов событий :**
```python
SPP_EVENT_MAP = {
    'CHECKIN':  CheckInEnum.DAY_START,
    'CHECKOUT': CheckInEnum.DAY_END,
}
```


### 2.3 Отпуска (LeaveRequest / Vacation)

| TCP-BPM | | |
|---|---|---|
| `LeaveRequest.start_date` | `DateField` | `startDate` |
| `LeaveRequest.end_date` | `DateField` | `endDate` |
| `LeaveRequest.status` | `LeaveStatusEnum` | `status` |
| `LeaveRequest.external_enbek_id` | `CharField` | `sppId` → добавить `external_spp_id` |
| `LeaveRequest.working_days_count` | `PositiveIntegerField` | `workingDays` |

---

## 3. Source of Truth

| Домен данных | Source of Truth | Направление синхронизации | Обоснование |
|---|---|---|---|
| **Персональные данные сотрудника** (ФИО, ИИН, дата рождения) | **Внешний HR** | TCP-BPM (read-only) | ИИН — государственный идентификатор, меняется в официальных системах |
| **Организационная структура** (Company, Department, Position) | **TCP-BPM** | TCP-BPM мастер, справочно | Структура настраивается внутри платформы |
| **Посещаемость (факт)** | **TCP-BPM** | TCP-BPM (push) или двунаправленно | Физические метки фиксируются нашей системой |
| **Начисления / Зарплата** | | TCP-BPM (read-only) | Финансовые данные — зона ответственности |
| **Отпуска (заявка)** | **TCP-BPM** | TCP-BPM | Заявка создаётся у нас и регистрируется|
| **Отпуска (статус утверждения)** | | TCP-BPM | Утверждение может происходить в БПМ|
| **Рабочий календарь** | **TCP-BPM** (`WorkCalendar`) | Локально, нет синхронизации | Уже реализован с поддержкой компании |

---

## 4. Схема обмена данными

### 4.1 Протокол и формат

```
TCP-BPM (Django/Celery)  ←→  Metrix (REST API)
       ↓
  JSON / HTTPS
  Timezone: Asia/Almaty (UTC+5)
  Date format: ISO 8601 (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS+05:00)
```

### 4.2 Направления потоков

```
┌─────────────────────────────────────────────────────────┐
│                     Metrix                              │
└──────────┬──────────────────────────────┬───────────────┘
           │ READ (pull)                  │ WRITE (push)
           ▼                              ▼
   ┌───────────────┐              ┌───────────────┐
   │  Сотрудники   │              │  Посещаемость │
   │  Начисления   │              │  Заявки на    │
   │  Статусы      │              │  отпуск       │
   │  отпусков     │              │               │
   └───────┬───────┘              └───────┬───────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────────┐
│              TCP-BPM (Django Backend)                   │
│                                                         │
│  apps/spp/         apps/hr/          apps/account/      │
│  ├─ client.py      ├─ models.py      ├─ models.py       │
│  ├─ sync.py        │  AttendanceRecord│  Employee        │
│  └─ tasks.py       │  LeaveRequest   │  iin (ключ)      │
└─────────────────────────────────────────────────────────┘
           │
           ▼
    Celery Beat (периодически: каждые 4ч)
```

### 4.3 Триггеры синхронизации

| Событие | Тип | Периодичность |
|---|---|---|
| Импорт сотрудников | Pull (Celery Beat) | Раз в 4 часа (по аналогии с 1С) |
| Импорт начислений | Pull (Celery Beat) | Раз в сутки (ночью) |
| Экспорт посещаемости | Push (сигнал / Celery) | После каждой отметки или батч раз в час |
| Экспорт заявок на отпуск  | Push (сигнал) | После изменения статуса |
| Получение статуса отпуска  Pull (Celery Beat) | Раз в час |

### 4.4 Структура нового приложения

```
backend/apps/spp/
├── __init__.py
├── apps.py
├── admin.py
├── client.py          # HTTP-клиент (по образцу onec/client_1c/client.py)
├── models.py          # SalaryRecord, SppSyncLog
├── serializers.py
├── sync.py            # Бизнес-логика синхронизации
├── tasks.py           # Celery-задачи
├── exceptions.py
├── migrations/
└── management/
    └── commands/
        └── sync_spp.py
```

---

## 5. Риски

| # | Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|---|
| R1 | **Нет публичного sandbox** — работает только с production-данными | Средняя | Высокое | Запросить тестовые данные / mock-окружение; реализовать mock-клиент для разработки |
| R2 | **Нет REST API** — использует SOAP, файловый обмен или очереди (Kafka/RabbitMQ) | Низкая | Критическое | Уточнить протокол, возможно потребуется адаптер |
| R3 | **Часовой пояс** — может отдавать UTC вместо Asia/Almaty | Средняя | Среднее | Явно указывать tz при десериализации; хранить в UTC (Django default), отображать в локальном |
| R4 | **Rate limiting** — ограничивает число запросов | Неизвестно | Среднее | Реализовать батчевую загрузку + retry с backoff (как в 1С-клиенте) |
| R5 | **Изменение API без уведомления** | Средняя | Высокое | Версионирование endpoint'ов; contract-тесты (responses-mock) |
| R6 | **Конфликт данных** — одна сущность изменена одновременно в двух системах | Средняя | Среднее | Чёткие правила source-of-truth (раздел 3); last-write-wins или флаг `sync_status` |
| R7 | **Недоступность** — интеграция блокирует основной функционал | Средняя | Высокое | Все вызовы — асинхронные через Celery; graceful degradation с логированием в `SppSyncLog` |
| R8 | **Закрытая сеть / VPN** —  доступен только из корпоративной сети | Средняя | Высокое | Уточнить сетевые требования; возможно потребуется VPN-туннель на сервере |
| R9| **Объём данных** — большое число сотрудников вызовет таймаут при первичной загрузке | Низкая | Среднее | Пагинация / sync-token (паттерн уже есть в 1С-клиенте) |

---

## 6. Оценка трудозатрат

### Фазы реализации

| Фаза | Задача | Оценка (SP) | Зависимости |
|---|---|---|---|
| **F1** | Реализация HTTP-клиента `SPPClient` + auth | 3 SP | ОВ-6 (документация) |
| **F2** | Модели `SalaryRecord`, `SppSyncLog` + миграции | 2 SP | F1 |
| **F3** | Sync-сервис: импорт сотрудников | 3 SP | F1, F2 |
| **F4** | Sync-сервис: импорт начислений | 3 SP | F1, F2 |
| **F5** | Экспорт посещаемости → СПП (push) | 3 SP | F1 |
| **F6** | Экспорт/синхронизация заявок на отпуск | 2 SP | F1 |
| **F7** | Celery-задачи + management command `sync_spp` | 2 SP | F3–F6 |
| **F8** | Тесты (mock-клиент, интеграционные) | 3 SP | F1–F7 |
| **F9** | Admin-панель + SppSyncLog UI | 1 SP | F2 |
| **ИТОГО** | | **22 SP** | |


### Сложность

- **Техническая:** Средняя — паттерн интеграции отработан, необходимо адаптировать.

---

## 7. Чеклист DoD

- [x] Структура проекта проанализирована
- [x] Существующие интеграции изучены как reference-паттерн
- [x] Mapping полей/сущностей подготовлен (предварительный)
- [x] Source of truth определён по каждому домену данных
- [x] Схема обмена данными описана
- [x] Риски зафиксированы
- [x] Оценка трудозатрат дана
- [ ] **API-документация СПП получена**
- [ ] **Sandbox-доступ получен**
- [ ] **Механизм auth подтверждён**
- [ ] **Сетевые требования (IP whitelist, VPN) подтверждены**
- [ ] Mapping скорректирован по реальной документации

---

## 8. Контакты и следующие шаги

1. Swagger / OpenAPI или Postman-коллекция API
2. URL sandbox-окружения и тестовые учётные данные
3. Механизм авторизации (OAuth2 / API Key / BasicAuth / MTLS)
4. Список поддерживаемых endpoint'ов с форматами данных
5. IP-адреса или подсети для whitelist
6. Ограничения rate limit
7. Расписание техобслуживания / SLA
