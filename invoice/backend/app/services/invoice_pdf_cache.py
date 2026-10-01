"""Кэш структурированных данных счёта (invoice_payload) для генерации PDF
без похода в живую 1С на каждый показ уже виденного счёта.

Слои:
    caller (nova_buh_1c_client.py / odata_1c_client.py download_invoice_file)
        -> get_cached_payload(): hit -> рендерим локально, 1С не трогаем
        -> miss/force -> сегодняшний живой каскад -> store_payload_if_valid()

Реквизиты поставщика (ИИК/БИК/КБе/банк/адрес/КНП/договор) — особый случай.
Эти поля объединяют 1С-данные и Tenant.invoice_* фоллбэк уже на этапе
сборки payload'а (см. nova_buh_1c_client._merge_supplier_requisites), и то,
что реально уходит в этот кэш, зависит от того, ОТКУДА взялось конкретное
значение:
  - Значение реально пришло из 1С (у Nova/COM — из org/COM-скрипта/MCP
    relay/OData-обогащения, см. _enrich_com_pdf_payload; у OData — прямо из
    Catalog_Организации, см. odata_1c_client._load_organization_details) —
    это стабильный 1С-состав, храним как есть, ничем не отличается от
    номера/строк/суммы.
  - Значение реально пришло из Tenant.invoice_* фоллбэка (1С само его не
    дало) — ЭТО кэшировать нельзя: правка банковского счёта в админке не
    применилась бы к уже закэшированным счетам — реальный риск "клиент
    платит на закрытый счёт", не гипотетика.
strip_tenant_sourced_fields() отличает первое от второго сравнением
значения с тем, что дал бы _merge_supplier_requisites на ПУСТОМ payload'е
(т.е. чистый фоллбэк без 1С) для этого же tenant — совпадает → это и есть
фоллбэк, вырезаем; отличается (или фоллбэк сам пуст) → это 1С-состав,
оставляем. Раньше эта функция вырезала все поля из TENANT_SOURCED_KEYS
безусловно, независимо от происхождения — баг, найденный 2026-09-01: у
всех реальных арендаторов Tenant.invoice_iik и т.п. пусты (миграция
f6a7b8c9d0e1 от 2026-05-29 их обнулила намеренно, "в PDF берутся из 1С"),
так что безусловное вырезание стирало РЕАЛЬНЫЕ банковские данные из 1С —
второй просмотр уже успешно открытого счёта либо падал в
MissingSupplierRequisitesError (Nova, есть гейт на чтении), либо тихо
рендерил PDF с пустым банком (OData, гейта на чтении нет). Get_cached_payload
всё равно домешивает текущего tenant заново при каждом чтении — то есть
"правка банка в админке применяется сразу" по-прежнему гарантировано, даже
когда конкретное поле в кэше уже несёт значение из 1С (домешивание не
трогает непустые поля, см. _merge_supplier_requisites: "if current: continue").

Важно: invoice_report.py._pick_from_1c для supplier_iik/bik/bank_name/kbe
НЕ имеет своего фоллбэка на tenant.* (в отличие от supplier_bin/name/address,
у которых свой инлайн-фоллбэк есть в самом рендерере) — единственное место,
где Tenant.invoice_iik и т.п. попадают в payload, это _merge_supplier_requisites.
Раньше её вызывал только Nova-путь при сборке payload'а "с нуля"; OData-путь
её не вызывал вообще. get_cached_payload() вызывает её всегда, для обоих
путей — то есть OData-арендаторы дополнительно ПОЛУЧАЮТ этот фоллбэк,
которого у них не было (осознанное расширение, не баг: сегодняшнее
отсутствие фоллбэка для OData выглядит как недосмотр, не как решение)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.invoice_pdf_payload import InvoicePdfPayload

logger = logging.getLogger(__name__)

# Эти поля никогда не персистятся — см. модульный докстринг. "supplier" —
# вложенный дублирующий словарь тех же полей, см.
# invoice_report.py._pick_from_1c (читает invoice[key] ИЛИ invoice["supplier"][key]).
TENANT_SOURCED_KEYS = (
    "supplier_name",
    "supplier_bin",
    "supplier_iik",
    "supplier_kbe",
    "supplier_bank_name",
    "supplier_bik",
    "supplier_address",
    "payment_knp",
    "contract_text",
    "supplier",
)

# Не чаще раза в это время на (tenant_id, invoice_id) — иначе force-refresh
# сам становится способом воспроизвести тот же Nova 502-шторм, от которого
# кэш и защищает (см. fix/whatsapp-pdf-retry-and-text-fallback, 2026-08-25/26).
FORCE_REFRESH_COOLDOWN = timedelta(minutes=5)

# Реальный баг 2026-09-14 (Astranium/"Toys market", счёт №00000003340): состав
# счёта (quantity/price/amount) до сих пор не имел вообще никакого TTL — в
# отличие от реквизитов поставщика (см. TENANT_SOURCED_KEYS), которые всегда
# домешиваются свежими, строки/суммы застывали в кэше НАВСЕГДА после первого
# fetch и никогда сами не обновлялись, даже когда 1С позже пересчитывала счёт
# (коммуналка — ТБО/теплоэнергия — часто досчитывается позже электричества/
# воды). Единственный выход был ручной force-refresh конкретным супер-админом.
# LINE_ITEMS_FRESHNESS_TTL закрывает это: закэшированный payload считается
# просроченным (и обновляется живым fetch'ем автоматически на следующий
# показ/отправку) после этого времени с момента последнего успешного fetch.
# Не 5 минут (как FORCE_REFRESH_COOLDOWN — это троттлинг ПОПЫТОК, не мера
# устаревания) — достаточно короткий, чтобы реально закрывать окно
# рассинхронизации, но не настолько короткий, чтобы массовая рассылка (см.
# feat/xlsx-phone-fallback-and-bulk-send, ~150 арендаторов разом) начала
# массово бить в живую 1С на каждый повторный показ того же счёта в рамках
# одного прогона — тот самый Nova 502-шторм, от которого кэш и защищает.
LINE_ITEMS_FRESHNESS_TTL = timedelta(minutes=30)


def _validate_invoice_id(invoice_id: str) -> str:
    """GUID-валидация до того, как значение уйдёт в SQL-запрос к этой
    таблице — тот же _guid_literal, что уже защищает OData-запросы (см.
    audit от 2026-08-25, commit baffdfb). Лениво импортирован — избегаем
    жёсткой зависимости этого модуля от конкретного 1С-клиента на уровне
    импорта."""
    from app.services.odata_1c_client import _guid_literal

    return _guid_literal(invoice_id, "invoice_id")


def strip_tenant_sourced_fields(payload: dict[str, Any], tenant=None) -> dict[str, Any]:
    """Чистая функция от payload+tenant, без БД (tenant передаётся как уже
    загруженный объект, не запрашивается здесь) — что реально уходит в кэш.

    tenant=None (не должно происходить у реальных вызывающих — оба
    caller'а в nova_buh_1c_client.py/odata_1c_client.py вызывают
    store_payload_if_valid только когда tenant is not None) — тогда сравнить
    не с чем, откатываемся к старому безусловному вырезанию как безопасному
    дефолту (лучше недокэшировать, чем случайно закэшировать чужой/неверный
    фоллбэк)."""
    if tenant is None:
        return {k: v for k, v in payload.items() if k not in TENANT_SOURCED_KEYS}

    from app.services.nova_buh_1c_client import _merge_supplier_requisites

    # "Чистый" tenant-фоллбэк без единого 1С-значения — эталон для сравнения.
    # {"_probe": True}, не {}: _merge_supplier_requisites само начинается с
    # `if not payload or tenant is None: return payload` — пустой словарь
    # falsy в Python, вызов с {} тихо вернул бы {} же, вообще не подмешав
    # tenant (нашли этим же тестом, который тут проверяет). Ключ "_probe"
    # не входит ни в одну пару этой функции, безвреден.
    tenant_only = _merge_supplier_requisites({"_probe": True}, tenant)

    cleaned = dict(payload)
    for key in TENANT_SOURCED_KEYS:
        if key == "supplier":
            # Вложенный дублирующий словарь (см. invoice_report.py._pick_from_1c)
            # — _merge_supplier_requisites его не трогает вообще, значит он
            # никогда не может быть tenant-фоллбэком; если он есть, это
            # всегда 1С-состав. Не вырезаем.
            continue
        current = str(cleaned.get(key) or "").strip()
        if not current:
            continue  # уже пусто — нечего вырезать, get_cached_payload домешает при чтении
        fallback = str(tenant_only.get(key) or "").strip()
        if current == fallback:
            del cleaned[key]
    return cleaned


def is_valid_pdf_payload(payload: Optional[dict[str, Any]]) -> bool:
    """Гейт валидности ДО записи в кэш. Каскад сборки payload'а сегодня —
    5+ независимых попыток (скрипт, COM MCP relay, OData enrichment,
    batch-фоллбэк), каждая из которых может тихо вернуть пусто и провалиться
    на следующий фоллбэк — нормально для одноразового живого рендера, но
    если это же самое закэшировать, деградация замораживается навсегда,
    пока кто-то случайно не заметит и не форснёт руками. Не проверяет
    реквизиты поставщика — они больше не часть 1С-обязательного состава
    (см. TENANT_SOURCED_KEYS), только реальный состав счёта."""
    if not payload:
        return False
    if not str(payload.get("number") or "").strip():
        return False
    if not str(payload.get("date") or "").strip():
        return False
    if not str(payload.get("counterparty_id") or "").strip():
        return False
    if payload.get("amount") is None:
        return False
    if not payload.get("items"):
        return False
    return True


def _get_row(db: Session, tenant_id: int, invoice_id: str) -> Optional[InvoicePdfPayload]:
    return (
        db.query(InvoicePdfPayload)
        .filter(
            InvoicePdfPayload.tenant_id == tenant_id,
            InvoicePdfPayload.invoice_id == invoice_id,
        )
        .first()
    )


def _row_is_stale(row: InvoicePdfPayload, ttl: timedelta) -> bool:
    if row.fetched_at is None:
        # Плейсхолдер-строка только для троттлинга force-refresh (payload
        # IS NULL) — "просрочка" тут бессмысленна, это не тот же случай.
        return False
    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at >= ttl


def get_cached_payload(db: Session, tenant, invoice_id: str) -> Optional[dict[str, Any]]:
    """Готовый к рендеру payload (реквизиты поставщика уже домешаны из
    ТЕКУЩЕЙ записи tenant) или None, если валидного кэша нет ИЛИ он старше
    LINE_ITEMS_FRESHNESS_TTL — в этом случае вызывающий код (Nova/OData
    download_invoice_file) должен интерпретировать None как "нужен живой
    fetch", как и в случае отсутствия кэша вовсе (см. модульный докстринг
    про баг 2026-09-14).

    tenant — сам объект Tenant, не только id: реквизиты мёржатся из него
    заново на каждое чтение, не сохраняются один раз при записи (см.
    модульный докстринг)."""
    invoice_id = _validate_invoice_id(invoice_id)
    row = _get_row(db, tenant.id, invoice_id)
    if not row or row.payload is None:
        return None
    if _row_is_stale(row, LINE_ITEMS_FRESHNESS_TTL):
        return None

    from app.services.nova_buh_1c_client import _merge_supplier_requisites

    return _merge_supplier_requisites(dict(row.payload), tenant)


def is_payload_cache_stale(db: Session, tenant_id: int, invoice_id: str) -> bool:
    """True только когда валидный закэшированный payload ЕСТЬ, но старше
    LINE_ITEMS_FRESHNESS_TTL — то есть get_cached_payload() вернула бы None
    именно из-за просрочки, а не потому что кэша не было вообще.

    Нужно вызывающим (пока — только Nova-клиенту), чтобы отличить эти два
    случая: "кэша никогда не было" — файловый PDF-кэш ниже (см.
    nova_buh_1c_client._try_reuse_cached_pdf) может служить как обычно, это
    не тот же баг; "кэш просрочен" — тот же файловый PDF-кэш мог быть
    перезаписан ЭТИМ ЖЕ путём при более раннем просмотре (каждый payload-
    cache-hit рендерит и перезаписывает PDF на диске заново, обновляя его
    mtime) — то есть его свежесть по mtime больше НЕ отражает реальную
    свежесть 1С-данных внутри, и его тоже нужно инвалидировать, иначе он
    молча замаскирует нужное обновление и живая 1С не будет вызвана вообще
    (тот же баг 2026-09-14, просто на слой ниже)."""
    invoice_id = _validate_invoice_id(invoice_id)
    row = _get_row(db, tenant_id, invoice_id)
    if not row or row.payload is None:
        return False
    return _row_is_stale(row, LINE_ITEMS_FRESHNESS_TTL)


def store_payload_if_valid(
    db: Session,
    tenant_id: int,
    invoice_id: str,
    payload: dict[str, Any],
    *,
    source: str,
    tenant: Any = None,
) -> bool:
    """True — записали. False — payload не прошёл гейт валидности, кэш НЕ
    тронут: существующая валидная строка (если была) переживает неудачный
    rehydrate как есть — никогда delete-then-write, тот же принцип, что уже
    применён в xlsx_import/upsert.py к tenant_payments.

    tenant — сам объект Tenant (не только id), нужен strip_tenant_sourced_fields
    чтобы отличить реальный 1С-состав реквизитов поставщика от
    tenant-фоллбэка (см. модульный докстринг). Оба реальных вызывающих
    (nova_buh_1c_client.py/odata_1c_client.py) уже имеют tenant в скоупе и
    передают его; tenant=None — только защитный дефолт для гипотетического
    вызывающего без него (откатывается к более консервативному безусловному
    вырезанию, см. strip_tenant_sourced_fields)."""
    if not is_valid_pdf_payload(payload):
        logger.warning(
            "invoice_pdf_cache: rehydrate вернул невалидный payload, кэш не тронут "
            "tenant_id=%s invoice_id=%s source=%s",
            tenant_id,
            invoice_id,
            source,
        )
        return False

    invoice_id = _validate_invoice_id(invoice_id)
    cleaned = strip_tenant_sourced_fields(payload, tenant)
    now = datetime.now(timezone.utc)

    row = _get_row(db, tenant_id, invoice_id)
    if row:
        row.payload = cleaned
        row.source = source
        row.fetched_at = now
    else:
        db.add(
            InvoicePdfPayload(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                payload=cleaned,
                source=source,
                fetched_at=now,
            )
        )
    db.commit()
    return True


def can_attempt_force_refresh(db: Session, tenant_id: int, invoice_id: str) -> bool:
    """False — попытка force-refresh на этот (tenant_id, invoice_id) была
    слишком недавно, отказать без похода в 1С вообще. Работает и для
    счетов, что ни разу не прошли гейт валидности (payload IS NULL) —
    именно ради этого случая last_force_refresh_attempt_at живёт в одной
    строке с payload, а не только там, где payload уже есть."""
    invoice_id = _validate_invoice_id(invoice_id)
    row = _get_row(db, tenant_id, invoice_id)
    if not row or not row.last_force_refresh_attempt_at:
        return True
    last = row.last_force_refresh_attempt_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last >= FORCE_REFRESH_COOLDOWN


def mark_force_refresh_attempted(db: Session, tenant_id: int, invoice_id: str) -> None:
    """Отмечает попытку независимо от исхода — неудачная попытка не должна
    давать право тут же попробовать ещё раз (см. can_attempt_force_refresh).
    Создаёт запись-плейсхолдер (payload=NULL), если её ещё не было —
    первый показ счёта вообще не значит "нечего троттлить", если он идёт
    через force=True."""
    invoice_id = _validate_invoice_id(invoice_id)
    row = _get_row(db, tenant_id, invoice_id)
    now = datetime.now(timezone.utc)
    if row:
        row.last_force_refresh_attempt_at = now
    else:
        db.add(
            InvoicePdfPayload(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                payload=None,
                source=None,
                fetched_at=None,
                last_force_refresh_attempt_at=now,
            )
        )
    db.commit()
