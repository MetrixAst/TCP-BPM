# Контракт QR-регистрации прихода/ухода (FE ⇄ BE)

Этот файл фиксирует контракт, под который уже написан FE (web + mobile) в рамках
Этап 2 / FE. Сам BE (модели, подпись токенов, scan API, anti-replay, idempotency,
аудит, права доступа) — отдельная задача (Этап 2 / BE) и в этой ветке не
реализован. До появления реального BE описанные ниже эндпоинты будут отвечать
404 — это ожидаемо.

## Модель

Kiosk-экран (планшет/монитор) устанавливается на точке входа (реестр QR-точек).
На экране постоянно показан QR-код, который **сам обновляется каждые ~20 сек**;
каждый раз в него зашит новый подписанный **короткоживущий токен** (TTL ~45 сек,
даёт запас на скан + сетевой round-trip). Статичный/напечатанный QR не подходит —
он не может быть "короткоживущим" и не даёт anti-replay.

Сотрудник сканирует экран точки входа **своим** устройством (телефон — Flutter,
либо любое устройство с камерой рядом со входом — web). Это не тот же экран, с
которого сканируют — kiosk и сканирующее устройство физически разные.

## Web: `POST /hr/attendance/qr-checkin/`

Session auth (тот же cookie-based auth, что и `/hr/attendance/checkin/`) + CSRF
(`X-CSRFToken` заголовок).

**Request** (`application/json`):
```json
{
  "event_type": "day_start | lunch_start | lunch_end | day_end",
  "token": "<строка, декодированная из QR>",
  "latitude": 43.1234567,
  "longitude": 76.1234567
}
```
`latitude`/`longitude` — опциональны (`null`, если геолокация недоступна/отклонена).

**Response 200**:
```json
{ "success": true, "message": "Отметка сохранена" }
```

**Response не-2xx**:
```json
{ "error": "<текст ошибки>" }
```
Формат идентичен `attendance_checkin`, чтобы существующая JS-обработка ошибок
(`attendance-qr-checkin.js`) работала без изменений.

## Mobile: `POST /api/v1/mobile/attendance/qr-checkin/`

JWT auth + `Idempotency-Key` заголовок (генерируется на клиенте, `uuid.v4()` на
каждый вызов — см. `mobile/lib/features/attendance/data/attendance_repository.dart`,
метод `checkinQr`).

**Request** (JSON, не multipart — фото нет):
```json
{
  "event_type": "day_start | lunch_start | lunch_end | day_end",
  "token": "<строка, декодированная из QR>",
  "latitude": 43.1234567,
  "longitude": 76.1234567
}
```

**Response 201**: тело в духе `AttendanceRecordOutSerializer` (как у обычного
чек-ина), плюс поле `source: "qr"`.

**Response 4xx/409**:
```json
{ "error": "<текст ошибки>" }
```

## Коды ошибок

FE уже обрабатывает эти сценарии (см. `attendance-qr-checkin.js` на web и
`AttendanceRepository._errorMessage()` на mobile), нужны ровно эти русские
тексты в `error` (или их варианты на web/mobile при необходимости):

| Сценарий | HTTP | `error` |
|---|---|---|
| Токен просрочен | 400 | `QR-код истёк, отсканируйте текущий код` |
| Токен недействителен / неизвестная точка / битая подпись | 400 | `Недействительный QR-код` |
| Токен уже был использован (anti-replay) | 409 | `Этот QR-код уже использован` |
| Нет профиля сотрудника | 403 | `Профиль сотрудника не найден` (уже используется в Face-флоу) |

## Источник отметки в истории

`AttendanceRecord` должна отдавать признак способа отметки (`face`/`qr`) на
каждую запись. FE уже верстает бейдж под это поле:

- web: `data-arrival-source`, `data-lunch-start-source`, `data-lunch-end-source`,
  `data-departure-source` атрибуты на строках `attendance_my.html` /
  `attendance_journal.html`, читает `attendance-modal.js`. Сейчас, пока BE не
  отдаёт поле, шаблон подставляет дефолт `face` для любого свершившегося
  события (`{{ item.arrival_source|default:'face' }}`) — корректно для всей
  существующей истории (она вся была Face). Когда появится реальное поле
  (например `item.arrival_source` из контекста вью), дефолт просто перестанет
  срабатывать и будет использовано настоящее значение.
- mobile: `AttendanceMark`/`AttendanceTodayStatus` пока не содержат поле
  источника — понадобится добавить при появлении его в ответе
  `/api/v1/mobile/attendance/today/`.
