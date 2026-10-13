# Metrix Auth Gateway

Единая точка входа мобильного приложения metriX для всех ТРЦ.
Пользователь вводит только логин и пароль — шлюз сам находит BPM-сервер
его ТРЦ. Список подключённых ТРЦ наружу не раскрывается.

## Как работает

1. Каждый BPM раз в час (и при изменении пользователей) отправляет в шлюз
   отпечатки логинов: `HMAC-SHA256(LOGIN_HASH_SECRET, логин)`. Сами логины
   в шлюз не попадают.
2. Приложение отправляет логин и пароль в `POST /api/login`.
3. Шлюз находит серверы с таким отпечатком, проверяет пароль на каждом
   (`/api/token/` BPM) и возвращает `access`, `refresh` и `base_url` того,
   где пароль подошёл. Дальше приложение работает с этим BPM напрямую.
4. На неизвестный логин и неверный пароль ответ одинаковый — 401
   «Неверный логин или пароль». Попытки входа ограничены по IP и логину.

## Запуск

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export LOGIN_HASH_SECRET=<длинный случайный секрет>   # тот же в .env всех BPM
export GATEWAY_DB_PATH=/data/gateway.sqlite3
.venv/bin/uvicorn gateway.main:app --host 0.0.0.0 --port 8010
```

Перед шлюзом — nginx с HTTPS, домен например `auth.metrix.com.ai`.

## Подключение BPM

```bash
.venv/bin/python -m gateway.cli add "ТРЦ Мега" https://bpm.mega.kz
```

Команда выдаёт `AUTH_GATEWAY_API_KEY`. В `.env` этого BPM:

```
AUTH_GATEWAY_URL=https://auth.metrix.com.ai
AUTH_GATEWAY_API_KEY=<ключ из команды>
AUTH_GATEWAY_LOGIN_SECRET=<тот же LOGIN_HASH_SECRET>
```

`python -m gateway.cli list` — серверы и число логинов,
`disable` / `enable <url>` — временно отключить сервер.

## Переменные

| Переменная | По умолчанию | |
|---|---|---|
| `LOGIN_HASH_SECRET` | — | обязательна |
| `GATEWAY_DB_PATH` | `gateway.sqlite3` | |
| `BACKEND_TIMEOUT` | `10` | секунд на запрос к BPM |
| `LOGIN_MAX_ATTEMPTS` | `10` | попыток входа за окно |
| `LOGIN_ATTEMPT_WINDOW` | `300` | окно, секунд |

## Тесты

```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest tests
```
