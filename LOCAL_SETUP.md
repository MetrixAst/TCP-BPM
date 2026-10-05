# Локальный запуск metriX BPM + сервис счетов

Краткая инструкция: поднять BPM, invoice-сервис на одном gateway и (опционально) мобильное web через ngrok.

## Что получится

| URL | Что это |
|-----|---------|
| http://localhost:8000 | BPM Django |
| http://localhost:8088 | Единый gateway (BPM + invoice) |
| http://localhost:8088/invoice-admin/ | Админка счетов |
| http://localhost:8088/invoice-portal/ | Кабинет арендатора |
| http://localhost:8088/invoice-api/docs | Swagger invoice API |
| http://localhost:8088/finances/invoices/ | Счета в BPM |

Публичный доступ: `ngrok http 8088`.

---

## 0. Требования

- Python 3.11+
- Docker + Docker Compose
- (опционально) Flutter 3.x, ngrok

---

## 1. BPM (Django)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Минимум в .env:
#   SECRET_KEY=dev
#   DEBUG=True
#   TZ=Asia/Almaty
#   ALLOWED_HOSTS=localhost,127.0.0.1,.ngrok-free.app
#   FINANCES_MENU_ENABLED=True
#   INVOICE_SERVICE_URL=http://127.0.0.1:8004
#   INVOICE_SERVICE_USERNAME=<из invoice/backend/.env.local SUPER_ADMIN_*>
#   INVOICE_SERVICE_PASSWORD=<из invoice/backend/.env.local>
#   INVOICE_SERVICE_TENANT_ID=3
#   INVOICE_SERVICE_TIMEOUT=30

python manage.py migrate
python manage.py createsuperuser   # если ещё нет
python manage.py runserver 0.0.0.0:8000
```

Без `POSTGRES_*` используется SQLite.

Меню **Финансы** видно при `FINANCES_MENU_ENABLED=True` и роли с правом `finances`.

---

## 2. Сервис счетов (invoice) + gateway

```bash
# из корня репозитория
python3 invoice/dev/make_env.py    # создаст invoice/backend/.env.local при необходимости

docker compose -f docker-compose.invoice.yml up -d --build
```

Gateway слушает **8088** и проксирует:

- `/` → BPM на `host.docker.internal:8000`
- `/invoice-api/` → FastAPI :8004
- `/invoice-admin/` → Vite-админка
- `/invoice-portal/` → Next-кабинет
- `/invoice-mock/` → заглушка Green API (WhatsApp)

Проверка:

```bash
curl -s http://127.0.0.1:8004/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/account/auth
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/invoice-admin/
```

Остановить контейнеры BPM из основного `docker-compose.yml`, если они тоже хотят порт **8000** (иначе локальный `runserver` не поднимется).

---

## 3. Связка BPM ↔ invoice (WhatsApp из карточки счёта)

В `backend/.env` должны быть `INVOICE_SERVICE_*` (см. выше). Логин/пароль берите из `invoice/backend/.env.local` (`SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD`).

Демо-данные финансов + телефоны в invoice:

```bash
cd backend && source .venv/bin/activate
python manage.py seed_finances_demo
```

В UI: **Финансы → Счета / Сервис счетов**. Отправка WhatsApp идёт через mock на `/invoice-mock/_requests`.

---

## 4. Ngrok (поделиться стендом)

Сначала BPM на `:8000` и compose invoice (gateway `:8088`), затем:

```bash
ngrok http 8088
```

Добавьте выданный HTTPS-хост в:

- `backend/.env` → `ALLOWED_HOSTS`, `TRUSTED_ORIGINS`
- при необходимости `CORS_ORIGINS` в `docker-compose.invoice.yml` у `invoice_api`, затем `docker compose -f docker-compose.invoice.yml up -d invoice_api`

После смены URL ngrok перезапустите Django (`runserver`).

Полезные пути на туннеле:

- `/account/auth` — вход BPM
- `/finances/invoices/` — счета
- `/invoice-admin/` — админка invoice
- `/app/` или `/m/` — Flutter web (если подняли, см. ниже)

---

## 5. Мобильное приложение (Flutter) — опционально

```bash
cd mobile
flutter pub get

# iOS / Android симулятор
flutter run --dart-define=BASE_URL=https://<ваш-ngrok-или-api-хост>

# Web-сборка для шаринга через тот же gateway
flutter build web --release \
  --base-href=/app/ \
  --dart-define=BASE_URL=https://<ваш-ngrok> \
  --no-web-resources-cdn
```

Раздача web (пример):

```bash
mkdir -p /tmp/metrix-web/app
cp -R build/web/. /tmp/metrix-web/app/
cd /tmp/metrix-web && python3 -m http.server 5555 --bind 0.0.0.0
```

В `invoice/gateway/nginx.conf` уже есть `location /app/` → `host.docker.internal:5555`. После правки конфига:

```bash
docker exec trc-invoice-gateway-1 nginx -s reload
```

На web отключены камера/QR/офлайн-очередь (native-only).

---

## 6. Типичные проблемы

| Симптом | Что проверить |
|---------|----------------|
| Gateway 502 на `/` | Не запущен `manage.py runserver` на 8000 |
| Порт 8000 занят | `docker stop django_backend` (или отключить restart у контейнера BPM) |
| Нет пункта Финансы | `FINANCES_MENU_ENABLED=True`, роль с правом finances, перелогин |
| WhatsApp «сервис недоступен» | invoice_api healthy, `INVOICE_SERVICE_*`, `seed_finances_demo` |
| CSRF / 400 через ngrok | хост в `ALLOWED_HOSTS` и `TRUSTED_ORIGINS` |
| Flutter web белый экран через ngrok | сборка с `--no-web-resources-cdn`, жёсткое обновление, путь `/app/` |

---

## Быстрый чеклист

```bash
# терминал 1 — BPM
cd backend && source .venv/bin/activate && python manage.py runserver 0.0.0.0:8000

# терминал 2 — invoice + gateway
docker compose -f docker-compose.invoice.yml up -d --build

# терминал 3 — публичный URL
ngrok http 8088
```

Готово: открывайте URL ngrok → логин в BPM → **Финансы**.
