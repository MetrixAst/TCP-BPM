#!/usr/bin/env python3
"""Разведка Green API: какие переменные/настройки реально отдаёт инстанс.

Дёргает только read-only GET-эндпоинты (ничего не меняет, не перезагружает
инстанс, не разлогинивает) и печатает ответ с расшифровкой каждого поля —
чтобы один раз посмотреть и понять, как Green API устроен, без похода в доки.

Источники учётных данных (проверяются в этом порядке):
  1. --id-instance/--api-token, переданные явно;
  2. --trc-id [--tenant-id] — тянет сохранённые в БД green_api_id_instance/
     green_api_api_token арендатора, иначе ТРЦ (тот же порядок, что и
     WhatsAppService.for_tenant/for_trc в проде);
  3. --test — тестовый инстанс из GREEN_API_TEST_ID_INSTANCE/_API_TOKEN (.env);
  4. без флагов — глобальный GREEN_API_ID_INSTANCE/_API_TOKEN (.env).

Запуск:
    python scripts/explore_green_api.py --trc-id 3
    python scripts/explore_green_api.py --id-instance 1101000001 --api-token XXXXXXXXXXXXXXXXXXXXXXXX
    python scripts/explore_green_api.py --test
    python scripts/explore_green_api.py --trc-id 3 --raw   # без пояснений, чистый JSON
    python scripts/explore_green_api.py --trc-id 3 --no-history   # без истории авторизаций

Ничего не отправляет и не мутирует — только getSettings/getStateInstance/
getWaSettings/getStateInstanceHistory. Токен в выводе всегда маскируется.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.catalog import TRC, Tenant  # noqa: E402


# Расшифровка полей — из доков green-api.com/en/docs/api/account/, чтобы не
# гадать, что значит stateInstance или зачем чему-то нужен delaySendMessagesMilliseconds.
FIELD_NOTES = {
    "getSettings": {
        "wid": "Идентификатор WhatsApp-аккаунта (номер + @c.us)",
        "webhookUrl": "Куда Green API шлёт вебхуки о входящих/статусах",
        "webhookUrlToken": "Значение заголовка авторизации для вебхуков",
        "delaySendMessagesMilliseconds": "Задержка между отправками сообщений, мс",
        "markIncomingMessagesReaded": "Автоматически отмечать входящие прочитанными",
        "markIncomingMessagesReadedOnReply": "Отмечать прочитанным при ответе через API",
        "outgoingWebhook": "Вебхук о статусах исходящих сообщений",
        "outgoingMessageWebhook": "Вебхук о сообщениях, отправленных с телефона",
        "outgoingAPIMessageWebhook": "Вебхук о сообщениях, отправленных через API",
        "incomingWebhook": "Вебхук о входящих сообщениях",
        "stateWebhook": "Вебхук о смене состояния авторизации инстанса",
        "keepOnlineStatus": "Показывать 'онлайн', даже когда телефон офлайн",
        "pollMessageWebhook": "Вебхук об опросах (poll)",
        "incomingCallWebhook": "Вебхук о входящих звонках",
        "editedMessageWebhook": "Вебхук об отредактированных сообщениях",
        "deletedMessageWebhook": "Вебхук об удалённых сообщениях",
        "catalogWebhook": "Вебхук о товарах/заказах каталога",
        "autoTyping": "Имитация набора текста, шкала 0-10",
        "linkPreview": "Показывать превью ссылок в сообщениях",
        "enableLidMode": "Использовать формат @lid для chatId",
    },
    "getStateInstance": {
        "stateInstance": (
            "authorized — подключён и работает; notAuthorized — не отсканирован QR; "
            "blocked — забанен; sleepMode — телефон выключен (до 5 мин на восстановление); "
            "starting — идёт запуск/обслуживание; suspended — временное ограничение"
        ),
    },
    "getWaSettings": {
        "avatar": "URL аватарки WhatsApp-аккаунта",
        "base64Avatar": "Та же аватарка, но в base64",
        "chatId": "lid текущего авторизованного аккаунта (пусто, если не авторизован)",
        "phone": "Номер телефона WhatsApp-аккаунта",
        "historySyncProgress": "Прогресс синхронизации истории чатов, %",
        "stateInstance": "То же, что в getStateInstance",
        "suspendedUntil": "Unix-timestamp окончания ограничения (только если suspended)",
        "deviceId": "Идентификатор устройства",
        "logoutProcess": "Идёт ли сейчас очистка данных (авторизация недоступна)",
    },
    "getStateInstanceHistory": {
        "stateInstance": "notAuthorized/authorized/blocked на момент этой записи",
        "timestamp": "Unix-время события (см. читаемую дату слева)",
        "phoneNumber": "Номер, к которому был привязан инстанс в этот момент",
    },
}

# Только чтение — ничего мутирующего (Reboot/Logout/SetSettings и т.п. сюда
# намеренно не включены).
ENDPOINTS = ["getSettings", "getStateInstance", "getWaSettings"]


def mask(token: str) -> str:
    if not token:
        return "<empty>"
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}…{token[-4:]}"


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str, str]:
    """Возвращает (id_instance, api_token, api_url, source_label)."""
    if args.id_instance and args.api_token:
        return args.id_instance, args.api_token, args.api_url or settings.GREEN_API_URL, "CLI"

    if args.trc_id:
        db = SessionLocal()
        try:
            tenant = None
            if args.tenant_id:
                tenant = (
                    db.query(Tenant)
                    .filter(Tenant.id == args.tenant_id, Tenant.trc_id == args.trc_id)
                    .first()
                )
            trc = db.query(TRC).filter(TRC.id == args.trc_id).first()
            if not trc:
                raise SystemExit(f"ТРЦ id={args.trc_id} не найден в БД")

            if tenant and tenant.green_api_id_instance and tenant.green_api_api_token:
                return (
                    tenant.green_api_id_instance,
                    tenant.green_api_api_token,
                    tenant.green_api_url or trc.green_api_url or settings.GREEN_API_URL,
                    f"арендатор «{tenant.name}» (id={tenant.id})",
                )
            if trc.green_api_id_instance and trc.green_api_api_token:
                return (
                    trc.green_api_id_instance,
                    trc.green_api_api_token,
                    trc.green_api_url or settings.GREEN_API_URL,
                    f"ТРЦ «{trc.name}» (id={trc.id})",
                )
            raise SystemExit(
                f"У ТРЦ «{trc.name}»"
                + (f" и арендатора «{tenant.name}»" if tenant else "")
                + " не заданы green_api_id_instance/green_api_api_token в БД"
            )
        finally:
            db.close()

    if args.test:
        if not settings.GREEN_API_TEST_ID_INSTANCE or not settings.GREEN_API_TEST_API_TOKEN:
            raise SystemExit(
                "GREEN_API_TEST_ID_INSTANCE/GREEN_API_TEST_API_TOKEN пусты в .env"
            )
        return (
            settings.GREEN_API_TEST_ID_INSTANCE,
            settings.GREEN_API_TEST_API_TOKEN,
            settings.GREEN_API_URL,
            "тестовый инстанс (.env)",
        )

    if settings.GREEN_API_ID_INSTANCE and settings.GREEN_API_API_TOKEN:
        return (
            settings.GREEN_API_ID_INSTANCE,
            settings.GREEN_API_API_TOKEN,
            settings.GREEN_API_URL,
            "глобальный инстанс (.env)",
        )

    raise SystemExit(
        "Не нашёл учётные данные Green API. Передайте --id-instance/--api-token, "
        "--trc-id [--tenant-id] или --test (см. --help)."
    )


def call(
    api_url: str,
    endpoint: str,
    id_instance: str,
    api_token: str,
    json_body: Optional[dict] = None,
):
    url = f"{api_url.rstrip('/')}/waInstance{id_instance}/{endpoint}/{api_token}"
    try:
        resp = requests.get(url, json=json_body, timeout=15)
    except requests.RequestException as exc:
        print(f"  ✗ {endpoint}: сетевая ошибка — {exc}")
        return None

    if resp.status_code != 200:
        print(f"  ✗ {endpoint}: HTTP {resp.status_code} — {resp.text[:300]}")
        return None

    try:
        return resp.json()
    except ValueError:
        print(f"  ✗ {endpoint}: ответ не JSON — {resp.text[:300]}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--id-instance", help="idInstance напрямую")
    parser.add_argument("--api-token", help="apiTokenInstance напрямую")
    parser.add_argument("--api-url", help="Базовый URL Green API (по умолчанию из .env)")
    parser.add_argument("--trc-id", type=int, help="Взять учётные данные из ТРЦ в БД")
    parser.add_argument(
        "--tenant-id", type=int, help="Уточнить арендатора внутри --trc-id (иначе берём ТРЦ)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Использовать GREEN_API_TEST_* из .env"
    )
    parser.add_argument(
        "--raw", action="store_true", help="Печатать только чистый JSON, без пояснений"
    )
    parser.add_argument(
        "--history-count",
        type=int,
        default=20,
        help="Сколько последних записей истории авторизации взять (default 20, у Green API — 100)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Не запрашивать getStateInstanceHistory (только settings/state/waSettings)",
    )
    args = parser.parse_args()

    id_instance, api_token, api_url, source = resolve_credentials(args)

    if not args.raw:
        print("=== Учётные данные ===")
        print("источник:      ", source)
        print("apiUrl:        ", api_url)
        print("idInstance:    ", id_instance)
        print("apiTokenInstance:", mask(api_token))
        print()

    results: dict[str, Optional[dict]] = {}
    for endpoint in ENDPOINTS:
        if not args.raw:
            print(f"=== {endpoint} ===")
        data = call(api_url, endpoint, id_instance, api_token)
        results[endpoint] = data
        if data is None:
            continue

        if args.raw:
            continue

        notes = FIELD_NOTES.get(endpoint, {})
        for key, value in data.items():
            note = notes.get(key, "")
            suffix = f"   # {note}" if note else ""
            print(f"  {key}: {value!r}{suffix}")
        print()

    if not args.no_history:
        if not args.raw:
            print("=== getStateInstanceHistory ===")
        history = call(
            api_url,
            "getStateInstanceHistory",
            id_instance,
            api_token,
            json_body={"count": args.history_count},
        )
        results["getStateInstanceHistory"] = history

        if history is not None and not args.raw:
            if not history:
                print("  (пусто — история не пишется или инстанс совсем новый)")
            for rec in history:
                ts = rec.get("timestamp")
                when = (
                    datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(ts, (int, float))
                    else "?"
                )
                phone = rec.get("phoneNumber", "—")
                print(f"  {when}  {rec.get('stateInstance')}  ({phone})")
            print()

    if args.raw:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
