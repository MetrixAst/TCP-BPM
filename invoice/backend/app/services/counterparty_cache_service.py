"""Кэш контрагентов из 1С в PostgreSQL: фоновый sync и быстрый ответ API."""
from __future__ import annotations

import copy
import logging
import time
from threading import Lock
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.counterparty_cache import CounterpartyCache
from app.services.counterparty_status_db import (
    invoice_counts_by_counterparty_from_db,
    latest_invoice_status_by_counterparty_from_db,
)
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id, tenant_uses_nova_org
from app.services.tenant_payment_types import (
    payment_due_days_for_tenant,
    tenant_payment_types_enabled,
)

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 60
# Если pod упал во время sync, status остаётся running и блокирует все новые sync.
SYNC_RUNNING_STALE_MINUTES = 45
_INVOICE_STATUS_CACHE: dict[str, tuple[float, dict[str, dict]]] = {}
_INVOICE_STATUS_CACHE_LOCK = Lock()


def fill_empty_phones_from_platform(
    db: Session,
    *,
    trc_id: int,
    items: list[dict[str, Any]],
) -> int:
    """
    Если phoneNumber из 1С пустой — подставить из counterparty_phones.

    Не перезаписывает номер, уже пришедший из 1С. Не трогает бизнес-логику sync.
    """
    if not trc_id or not items:
        return 0

    from app.models.catalog import CounterpartyPhone
    from app.services.phone_list import split_phone_values

    rows = (
        db.query(CounterpartyPhone)
        .filter(CounterpartyPhone.trc_id == trc_id)
        .all()
    )
    by_id: dict[str, str] = {}
    for row in rows:
        phones = split_phone_values(row.phone or "")
        if not phones:
            continue
        key = (row.one_c_counterparty_id or "").strip().lower()
        if key and key not in by_id:
            by_id[key] = phones[0]

    if not by_id:
        return 0

    filled = 0
    for cp in items:
        current = (cp.get("phoneNumber") or cp.get("phone") or "").strip()
        if current:
            continue
        phone = by_id.get((cp.get("id") or "").strip().lower())
        if not phone:
            continue
        cp["phoneNumber"] = phone
        filled += 1
    return filled


def attach_last_whatsapp_sent(
    db: Session,
    *,
    trc_id: Optional[int],
    items: list[dict[str, Any]],
) -> None:
    """lastWhatsappSentAt на каждый item — последняя успешная отправка WhatsApp
    этому контрагенту (любого вида, см. whatsapp_jobs.py).

    Только для живого ответа API (get_counterparties_api_response) — специально
    НЕ вызывается из sync-пути (run_counterparty_cache_sync), иначе значение
    запечётся в CounterpartyCache.data и устареет уже после следующей отправки,
    до следующего полного sync (кэш обновляется раз в час).
    """
    if not trc_id or not items:
        return

    from app.models.catalog import CounterpartyPhone

    rows = (
        db.query(CounterpartyPhone)
        .filter(
            CounterpartyPhone.trc_id == trc_id,
            CounterpartyPhone.last_whatsapp_sent_at.isnot(None),
        )
        .all()
    )
    if not rows:
        return
    last_sent_by_id = {
        (row.one_c_counterparty_id or "").strip().lower(): row.last_whatsapp_sent_at
        for row in rows
        if row.one_c_counterparty_id
    }
    if not last_sent_by_id:
        return
    for cp in items:
        last_sent = last_sent_by_id.get((cp.get("id") or "").strip().lower())
        if last_sent:
            cp["lastWhatsappSentAt"] = last_sent.isoformat()


def attach_auto_notify_paused(
    db: Session,
    *,
    trc_id: Optional[int],
    items: list[dict[str, Any]],
) -> None:
    """autoNotifyPaused на каждый item — арендатор поставил авто-рассылку на
    паузу для этого контрагента (кнопка в invoice-client), см.
    CounterpartyPhone.auto_notify_paused / AutoNotificationService.

    Как и attach_last_whatsapp_sent — только для живого ответа API, не для
    sync-пути, иначе значение запечётся в CounterpartyCache.data и устареет."""
    if not trc_id or not items:
        return

    from app.models.catalog import CounterpartyPhone

    rows = (
        db.query(CounterpartyPhone)
        .filter(
            CounterpartyPhone.trc_id == trc_id,
            CounterpartyPhone.auto_notify_paused.is_(True),
        )
        .all()
    )
    if not rows:
        return
    paused_ids = {
        (row.one_c_counterparty_id or "").strip().lower()
        for row in rows
        if row.one_c_counterparty_id
    }
    if not paused_ids:
        return
    for cp in items:
        if (cp.get("id") or "").strip().lower() in paused_ids:
            cp["autoNotifyPaused"] = True


_INVOICE_STATUS_CACHE_TTL_SEC = 300


def _invoice_status_cache_key(tenant_id: int, period: Optional[str]) -> str:
    return f"{tenant_id}:{period or ''}"


def invalidate_invoice_status_cache(
    tenant_id: Optional[int] = None,
    period: Optional[str] = None,
) -> None:
    with _INVOICE_STATUS_CACHE_LOCK:
        if tenant_id is None and period is None:
            _INVOICE_STATUS_CACHE.clear()
            return
        keys = list(_INVOICE_STATUS_CACHE.keys())
        for key in keys:
            if tenant_id is not None and not key.startswith(f"{tenant_id}:"):
                continue
            if period is not None and not key.endswith(f":{period}"):
                continue
            _INVOICE_STATUS_CACHE.pop(key, None)


def _get_cached_invoice_status(cache_key: str) -> Optional[dict[str, dict]]:
    with _INVOICE_STATUS_CACHE_LOCK:
        entry = _INVOICE_STATUS_CACHE.get(cache_key)
        if not entry:
            return None
        ts, data = entry
        if time.time() - ts > _INVOICE_STATUS_CACHE_TTL_SEC:
            _INVOICE_STATUS_CACHE.pop(cache_key, None)
            return None
        return data


def _set_cached_invoice_status(cache_key: str, data: dict[str, dict]) -> None:
    with _INVOICE_STATUS_CACHE_LOCK:
        _INVOICE_STATUS_CACHE[cache_key] = (time.time(), data)


def _fetch_live_invoice_status_by_cp(
    db: Session,
    *,
    tenant_id: int,
    tenant,
    period: Optional[str],
) -> dict[str, dict]:
    integration = get_integration_for_tenant(db, tenant_id)
    client = integration.client if integration else None
    if not client or not hasattr(client, "get_latest_invoice_status_by_counterparty"):
        return {}
    try:
        if not client.access_token:
            client.authenticate()
        due_days = payment_due_days_for_tenant(tenant) if tenant else {}
        return client.get_latest_invoice_status_by_counterparty(
            due_day=due_days.get("rent", 5),
            period=period,
            utilities_due_day=due_days.get("utilities"),
            operations_due_day=due_days.get("operations"),
        )
    except Exception as exc:
        logger.warning("Live invoice status failed tenant_id=%s period=%s: %s", tenant_id, period, exc)
        return {}
    finally:
        if integration and hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass


def _append_virtual_counterparties(
    items: list[dict[str, Any]],
    *,
    invoice_status_by_cp: dict[str, dict],
    invoice_counts: dict[str, int],
    tenant,
) -> None:
    from app.services.counterparty_name_match import is_virtual_counterparty_id

    existing_ids = {(cp.get("id") or "").strip().lower() for cp in items}
    due_days = payment_due_days_for_tenant(tenant) if tenant else {
        "rent": 5,
        "utilities": 5,
        "operations": 5,
    }
    enabled = tenant_payment_types_enabled(tenant) if tenant else {
        "rent": True,
        "utilities": True,
        "operations": True,
    }

    for cp_key, latest in invoice_status_by_cp.items():
        if not is_virtual_counterparty_id(cp_key):
            continue
        if cp_key in existing_ids:
            continue
        display_name = (latest.get("counterpartyName") or "").strip() or "Контрагент без привязки к 1С"
        items.append(
            {
                "id": cp_key,
                "fullName": display_name,
                "virtual": True,
                "invoiceCount": invoice_counts.get(cp_key, 1),
                "latestInvoice": latest,
                "paymentDueDays": dict(due_days),
                "paymentTypesEnabled": enabled,
                "bin": "",
                "iin": "",
                "phoneNumber": "",
                "bankAccounts": [],
                "contracts": [],
            }
        )


def _resolve_invoice_status_by_cp(
    db: Session,
    *,
    tenant_id: Optional[int],
    tenant,
    period: Optional[str],
) -> dict[str, dict]:
    """Статусы счетов для таблицы контрагентов — только из БД (после sync)."""
    return latest_invoice_status_by_counterparty_from_db(
        db,
        tenant_id=tenant_id,
        period=period,
    )


def current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


def _get_or_create_row(db: Session, tenant_id: int) -> CounterpartyCache:
    row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    if row:
        return row
    row = CounterpartyCache(tenant_id=tenant_id, status="idle")
    db.add(row)
    db.flush()
    return row


def build_counterparty_payloads(
    *,
    counterparties,
    tenant,
    contracts_by_cp: dict,
    invoice_counts_by_cp: Optional[dict] = None,
) -> list[dict[str, Any]]:
    invoice_counts_by_cp = invoice_counts_by_cp or {}
    result: list[dict[str, Any]] = []
    for counterparty in counterparties:
        full_name = (counterparty.full_name or "").strip()
        if not full_name or full_name.startswith("Индивидуальные предприниматели"):
            continue

        phone = counterparty.phone_number or counterparty.phone

        bank_accounts = []
        if counterparty.bank_accounts:
            bank_accounts = [
                {
                    "id": acc.id,
                    "bank_name": acc.bank_name,
                    "bank_bik": acc.bank_bik,
                    "account_number": acc.account_number,
                    "currency": acc.currency,
                    "is_default": acc.is_default,
                }
                for acc in counterparty.bank_accounts
            ]
        elif counterparty.account_number:
            bank_accounts = [
                {
                    "id": counterparty.id,
                    "bank_name": "",
                    "bank_bik": counterparty.bic,
                    "account_number": counterparty.account_number,
                    "currency": counterparty.currency or "KZT",
                    "is_default": True,
                }
            ]

        cp_key = (counterparty.id or "").strip().lower()

        contracts = []
        if cp_key in contracts_by_cp:
            contracts = contracts_by_cp[cp_key]
        elif counterparty.contracts:
            contracts = [
                {
                    "id": contract.id,
                    "number": contract.number,
                    "date": contract.date,
                    "type": contract.type,
                    "name": contract.name,
                }
                for contract in counterparty.contracts
            ]
        elif counterparty.contract_number:
            contracts = [
                {
                    "id": counterparty.id,
                    "number": counterparty.contract_number,
                    "date": counterparty.contract_date,
                    "type": counterparty.counterparty_type,
                    "name": counterparty.price_type,
                }
            ]

        invoice_count = invoice_counts_by_cp.get(cp_key, 0)

        item: dict[str, Any] = {
            "id": counterparty.id,
            "fullName": full_name,
            "contactPerson": counterparty.short_name or "",
            "bin": counterparty.bin,
            "iin": counterparty.rnn or "",
            "address": counterparty.address,
            "phoneNumber": phone,
            "email": counterparty.email,
            "bankAccounts": bank_accounts,
            "contracts": contracts,
            "invoiceCount": invoice_count,
            "govEntity": counterparty.gov_entity,
            "vatCertDate": counterparty.vat_cert_date,
            "kbe": counterparty.kbe,
            "vatCertNo": counterparty.vat_cert_no,
            "rnn": counterparty.rnn,
            "vatSeries": counterparty.vat_series,
            "residencyCountry": counterparty.residency_country,
            "counterpartyType": counterparty.counterparty_type,
            "accountNumber": counterparty.account_number,
            "bic": counterparty.bic,
            "contractNumber": counterparty.contract_number,
            "contractDate": counterparty.contract_date,
            "currency": counterparty.currency,
            "priceType": counterparty.price_type,
            "paymentDueDays": payment_due_days_for_tenant(tenant) if tenant else {
                "rent": 5,
                "utilities": 5,
                "operations": 5,
            },
        }
        folder_id = (getattr(counterparty, "parent", None) or "").strip()
        folder_name = (getattr(counterparty, "folder_name", None) or "").strip()
        if folder_id and folder_id.replace("-", "").strip("0") != "":
            item["folderId"] = folder_id
        if folder_name:
            item["folderName"] = folder_name
        result.append(item)
    return result


def find_counterparty_in_cache(
    db: Session,
    tenant_id: int,
    counterparty_id: str,
) -> Optional[dict[str, Any]]:
    """Один контрагент из PostgreSQL-кэша (без запроса в 1С)."""
    cp_key = (counterparty_id or "").strip().lower()
    if not tenant_id or not cp_key:
        return None
    row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    if not row or not row.data:
        return None
    for item in row.data:
        if (item.get("id") or "").strip().lower() == cp_key:
            return copy.deepcopy(item)
    return None


def _cache_is_stale(row: Optional[CounterpartyCache]) -> bool:
    if not row or not row.synced_at:
        return True
    if row.status == "failed":
        return True
    age = datetime.now(timezone.utc) - row.synced_at.replace(tzinfo=timezone.utc)
    return age.total_seconds() >= CACHE_TTL_MINUTES * 60


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def clear_stale_counterparty_sync(db: Session, tenant_id: int) -> bool:
    """Сбросить зависший sync (status=running после падения pod / 504)."""
    row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    if not row or row.status != "running":
        return False

    now = datetime.now(timezone.utc)
    started = _as_utc(row.started_at)
    if started:
        age_sec = (now - started).total_seconds()
    else:
        synced = _as_utc(row.synced_at)
        age_sec = (now - synced).total_seconds() if synced else SYNC_RUNNING_STALE_MINUTES * 60 + 1

    if age_sec < SYNC_RUNNING_STALE_MINUTES * 60:
        return False

    row.status = "failed"
    row.error = (
        "Синхронизация прервана (предыдущий запуск не завершился). "
        "Нажмите «Обновить из 1С» ещё раз."
    )
    row.synced_at = now
    db.commit()
    logger.warning(
        "Cleared stale counterparty sync tenant_id=%s age_sec=%.0f",
        tenant_id,
        age_sec,
    )
    return True


def set_counterparty_sync_running(db: Session, tenant_id: int) -> bool:
    clear_stale_counterparty_sync(db, tenant_id)
    row = _get_or_create_row(db, tenant_id)
    if row.status == "running":
        return False
    row.status = "running"
    row.error = None
    row.started_at = datetime.now(timezone.utc)
    db.commit()
    return True


def set_counterparty_sync_done(db: Session, tenant_id: int, payloads: list[dict], total: int) -> None:
    row = _get_or_create_row(db, tenant_id)
    now = datetime.now(timezone.utc)
    # xlsx-контрагенты (source="xlsx", см. sync_xlsx_counterparty_directory)
    # переживают live-синк 1С — тот же принцип, что и
    # counterparty_balance_service.replace_balances_for_tenant уже применяет
    # к CounterpartyBalance: 1С-синк продолжает идти в фоне как есть
    # (prefer_xlsx/fallback_on_1c_failure тенант может иметь и то, и то), но
    # не должен молча стирать контрагентов, которых xlsx-импорт сам завёл
    # (row.data — блин перезаписи, не merge, без этой строчки следующий же
    # синк снёс бы их).
    existing_xlsx = [item for item in (row.data or []) if item.get("source") == "xlsx"]
    row.data = list(payloads) + existing_xlsx
    row.total_from_1c = total
    row.status = "done"
    row.error = None
    row.synced_at = now
    db.commit()


def compute_xlsx_counterparty_entries(normalized_rows) -> dict[str, dict[str, Any]]:
    """Чистая функция (без БД) — cp_id -> элемент CounterpartyCache.data
    для xlsx-строк, что не сопоставились ни с одним реальным 1С-контрагентом
    (row.matched is False, counterparty_id — "virtual:...", см.
    xlsx_import/normalize.py). Отдельно от sync_xlsx_counterparty_directory
    специально ради тестов — CounterpartyCache.data Postgres-only JSONB, не
    рендерится на in-memory SQLite тестовой БД (см. tests/conftest.py про
    то же самое ограничение), а эта часть логики от Postgres не зависит.

    normalized_rows — list[NormalizedRow], без прямого импорта типа (см.
    докстринг sync_xlsx_counterparty_directory про cycle с xlsx_import)."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in normalized_rows:
        if row.matched:
            continue
        cp_id = row.counterparty_id
        if not cp_id:
            continue
        bin_value = getattr(row.source_row, "bin_value", None) or ""
        phone_value = getattr(row.source_row, "phone", None) or ""
        entry = by_id.get(cp_id)
        if entry is None:
            entry = {
                "id": cp_id,
                "fullName": row.ip_name,
                "bin": bin_value,
                "iin": "",
                "phoneNumber": phone_value,
                "bankAccounts": [],
                "contracts": [],
                "invoiceCount": 0,
                "source": "xlsx",
            }
            by_id[cp_id] = entry
        entry["invoiceCount"] += 1
        if bin_value and not entry["bin"]:
            entry["bin"] = bin_value
        if phone_value and not entry["phoneNumber"]:
            entry["phoneNumber"] = phone_value
    return by_id


def sync_xlsx_counterparty_directory(db: Session, tenant_id: int, normalized_rows) -> int:
    """Апсертит в CounterpartyCache.data контрагентов, вычисленных
    compute_xlsx_counterparty_entries() (см. её докстринг про matched/
    virtual:).

    Раньше БИН/имя из файла использовались ТОЛЬКО для матчинга внутри
    normalize() и нигде не сохранялись — контрагент из xlsx физически не
    существовал нигде, кроме поля tenant_payments.tenant_name, поэтому
    вкладка «Контрагенты»/«Взаиморасчёты» ничего не показывала для
    xlsx-only арендатора.

    Полная замена, тот же принцип, что upsert.py/balances.py: контрагент,
    ушедший из файла (не встретился в этой загрузке), из списка убирается —
    иначе он висел бы здесь вечно после переключения на другой файл.
    Реальные 1С-контрагенты (item без "source": "xlsx") не трогаются.

    normalized_rows пуст целиком (0 строк из файла — почти всегда битый/не
    тот файл, см. upsert.py) — не трогаем ничего вообще, тот же guard, что
    и там; пустой результат compute_xlsx_counterparty_entries() при
    НЕпустых normalized_rows (все строки реально сопоставились с 1С) —
    легитимный случай, тогда старые xlsx-элементы корректно вычищаются."""
    if not normalized_rows:
        return 0

    by_id = compute_xlsx_counterparty_entries(normalized_rows)

    cache_row = _get_or_create_row(db, tenant_id)
    non_xlsx = [item for item in (cache_row.data or []) if item.get("source") != "xlsx"]
    cache_row.data = non_xlsx + list(by_id.values())
    db.commit()
    return len(by_id)


def set_counterparty_sync_failed(db: Session, tenant_id: int, error: str) -> None:
    row = _get_or_create_row(db, tenant_id)
    row.status = "failed"
    row.error = error
    row.synced_at = datetime.now(timezone.utc)
    db.commit()


def run_counterparty_cache_sync(tenant_id: int, limit: int = 10000) -> int:
    """Фоновая загрузка контрагентов из 1С в PostgreSQL."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    integration = None
    try:
        if not set_counterparty_sync_running(db, tenant_id):
            logger.info("Counterparty sync already running tenant_id=%s", tenant_id)
            return -1

        integration = get_integration_for_tenant(db, tenant_id)
        tenant = get_tenant_by_id(db, tenant_id)
        if not integration.client:
            raise RuntimeError("1C client not available")

        if not integration.client.access_token:
            integration.client.authenticate()

        counterparties = integration.client.get_counterparties(limit=limit)
        try:
            from app.services.counterparty_folder_enrichment import (
                enrich_counterparties_with_folders,
            )

            nova_client = integration.client if getattr(integration, "_uses_nova", False) else None
            enrich_counterparties_with_folders(
                counterparties,
                tenant=tenant,
                nova_client=nova_client,
            )
        except Exception as exc:
            logger.warning(
                "Counterparty folder enrich skipped tenant_id=%s: %s",
                tenant_id,
                exc,
            )

        contracts_by_cp: dict = {}
        if hasattr(integration.client, "get_contracts_by_counterparty"):
            contracts_by_cp = integration.client.get_contracts_by_counterparty()

        invoice_counts_by_cp: dict[str, int] = {}
        if hasattr(integration.client, "get_invoice_counts_by_counterparty"):
            try:
                invoice_counts_by_cp = integration.client.get_invoice_counts_by_counterparty()
            except Exception as exc:
                logger.warning(
                    "Invoice counts by counterparty failed tenant_id=%s: %s",
                    tenant_id,
                    exc,
                )

        payloads = build_counterparty_payloads(
            counterparties=counterparties,
            tenant=tenant,
            contracts_by_cp=contracts_by_cp,
            invoice_counts_by_cp=invoice_counts_by_cp,
        )
        if tenant and tenant.trc_id:
            filled = fill_empty_phones_from_platform(
                db, trc_id=tenant.trc_id, items=payloads
            )
            if filled:
                logger.info(
                    "Counterparty cache: filled %s empty phones from platform tenant_id=%s",
                    filled,
                    tenant_id,
                )
        set_counterparty_sync_done(db, tenant_id, payloads, len(payloads))
        logger.info(
            "Counterparty cache synced tenant_id=%s records=%s",
            tenant_id,
            len(payloads),
        )
        # после контрагентов подтягиваем взаиморасчёты (debit/credit), мягко
        try:
            from app.services.counterparty_balance_service import (
                sync_counterparty_balances,
            )

            sync_counterparty_balances(db, tenant_id)
        except Exception as bal_exc:
            logger.warning(
                "Balance sync after counterparties skipped tenant_id=%s: %s",
                tenant_id,
                bal_exc,
            )
        return len(payloads)
    except Exception as exc:
        logger.exception("Counterparty cache sync failed tenant_id=%s", tenant_id)
        set_counterparty_sync_failed(db, tenant_id, str(exc))
        raise
    finally:
        if integration and hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass
        db.close()


def get_counterparties_api_response(
    db: Session,
    *,
    tenant_id: Optional[int],
    tenant,
    limit: int,
    include_invoice_status: bool,
    period: Optional[str],
    warning: Optional[str] = None,
) -> dict[str, Any]:
    row = None
    if tenant_id:
        clear_stale_counterparty_sync(db, tenant_id)
        row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()

    raw_items = list(row.data or []) if row and row.data else []
    items = copy.deepcopy(raw_items[:limit])

    if tenant and getattr(tenant, "trc_id", None) and items:
        fill_empty_phones_from_platform(db, trc_id=tenant.trc_id, items=items)
        attach_last_whatsapp_sent(db, trc_id=tenant.trc_id, items=items)
        attach_auto_notify_paused(db, trc_id=tenant.trc_id, items=items)

    invoice_counts: dict[str, int] = {}
    if tenant_id:
        invoice_counts = invoice_counts_by_counterparty_from_db(
            db,
            tenant_id=tenant_id,
            period=period,
        )
        for cp in items:
            cp_key = (cp.get("id") or "").strip().lower()
            count = invoice_counts.get(cp_key)
            if count:
                cp["invoiceCount"] = max(int(cp.get("invoiceCount") or 0), count)

    invoice_status_by_cp: dict[str, dict] = {}
    if include_invoice_status:
        invoice_status_by_cp = _resolve_invoice_status_by_cp(
            db,
            tenant_id=tenant_id,
            tenant=tenant,
            period=period,
        )
        for cp in items:
            cp_key = (cp.get("id") or "").strip().lower()
            latest = invoice_status_by_cp.get(cp_key)
            if latest:
                if not latest.get("invoiceDate") and latest.get("dueDate"):
                    latest = dict(latest)
                    latest["invoiceDate"] = latest.get("dueDate")
                cp["latestInvoice"] = latest
        _append_virtual_counterparties(
            items,
            invoice_status_by_cp=invoice_status_by_cp,
            invoice_counts=invoice_counts,
            tenant=tenant,
        )

    # BUH balance: debit/credit/net рядом со счетами (счета не переписываем)
    balance_synced_at: Optional[str] = None
    if tenant_id:
        try:
            from app.services.counterparty_balance_service import balances_map_for_tenant

            bal_map = balances_map_for_tenant(db, tenant_id)
            for cp in items:
                cp_key = (cp.get("id") or "").strip().lower()
                bal = bal_map.get(cp_key)
                if not bal:
                    continue
                cp["balanceDebit"] = bal["debit"]
                cp["balanceCredit"] = bal["credit"]
                cp["balanceNet"] = bal["net"]
                cp["balanceLabel"] = bal["label"]
                if bal.get("syncedAt") and not balance_synced_at:
                    balance_synced_at = bal["syncedAt"]
        except Exception as bal_exc:
            logger.debug("balance attach skipped: %s", bal_exc)

    folders: list[dict[str, str]] = []
    seen_folders: set[str] = set()
    for cp in items:
        folder_name = (cp.get("folderName") or "").strip()
        folder_id = (cp.get("folderId") or "").strip()
        if not folder_name:
            continue
        key = folder_name.casefold()
        if key in seen_folders:
            continue
        seen_folders.add(key)
        folders.append({"id": folder_id, "fullName": folder_name})
    folders.sort(key=lambda f: f["fullName"].casefold())

    # Если в кэше ещё нет folderName — показать папки из Nova groups (fullName групп).
    if not folders and tenant and tenant_uses_nova_org(tenant):
        try:
            integration = get_integration_for_tenant(db, tenant.id)
            client = integration.client
            if client and hasattr(client, "get_counterparty_groups"):
                for group in client.get_counterparty_groups() or []:
                    name = (group.get("fullName") or "").strip()
                    if not name:
                        continue
                    key = name.casefold()
                    if key in seen_folders:
                        continue
                    seen_folders.add(key)
                    folders.append(
                        {
                            "id": str(group.get("id") or "").strip(),
                            "fullName": name,
                        }
                    )
                folders.sort(key=lambda f: f["fullName"].casefold())
        except Exception as exc:
            logger.debug("counterparty folders from Nova groups unavailable: %s", exc)

    payload: dict[str, Any] = {
        "counterparties": items,
        "folders": folders,
        "total_from_1c": row.total_from_1c if row else len(items),
        "source": "database" if raw_items else "Catalog_Контрагенты",
        "sync_status": row.status if row else "idle",
    }
    if tenant:
        enabled = tenant_payment_types_enabled(tenant)
        due_days = payment_due_days_for_tenant(tenant)
        payload["paymentTypesEnabled"] = enabled
        payload["tenantAutoNotifyPaused"] = bool(getattr(tenant, "auto_notify_paused", False))
        for cp in payload["counterparties"]:
            cp["paymentDueDays"] = dict(due_days)
            cp["paymentTypesEnabled"] = enabled
    if row and row.synced_at:
        payload["synced_at"] = row.synced_at.isoformat()
    if balance_synced_at:
        payload["balance_synced_at"] = balance_synced_at
    if row and row.error and row.status == "failed":
        payload["sync_error"] = row.error
    if warning:
        payload["warning"] = warning
    return payload


def get_cached_directory_items(db: Session, tenant_id: int) -> list[dict[str, str]]:
    row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    if not row or not row.data:
        return []
    tenant = get_tenant_by_id(db, tenant_id)
    data = copy.deepcopy(list(row.data or []))
    if tenant and tenant.trc_id:
        fill_empty_phones_from_platform(db, trc_id=tenant.trc_id, items=data)
    items: list[dict[str, str]] = []
    for cp in data:
        cp_id = cp.get("id")
        full_name = (cp.get("fullName") or "").strip()
        if not cp_id or not full_name:
            continue
        items.append(
            {
                "one_c_counterparty_id": cp_id,
                "counterparty_name": full_name,
                "contact_name": cp.get("contactPerson") or "",
                "bin_value": cp.get("bin") or cp.get("iin") or "",
                "phone_number": (cp.get("phoneNumber") or cp.get("phone") or "").strip(),
            }
        )
    return items


def request_counterparty_cache_sync(db: Session, tenant_id: int) -> bool:
    """Запуск sync контрагентов в фоне (не блокирует HTTP), как payment sync."""
    import threading

    from app.core.config import settings
    from app.services.job_queue import enqueue_counterparty_sync

    clear_stale_counterparty_sync(db, tenant_id)
    row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    if row and row.status == "running":
        return False

    if settings.KAFKA_ENABLED:
        if not set_counterparty_sync_running(db, tenant_id):
            return False
        if enqueue_counterparty_sync(tenant_id=tenant_id):
            logger.info("Counterparty sync queued tenant_id=%s", tenant_id)
            return True
        set_counterparty_sync_failed(db, tenant_id, "Не удалось поставить задачу в очередь Kafka")
        return False

    def _run() -> None:
        try:
            run_counterparty_cache_sync(tenant_id)
        except Exception as exc:
            logger.exception("Background counterparty sync failed tenant_id=%s: %s", tenant_id, exc)

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"counterparty-sync-{tenant_id}",
    ).start()
    logger.info("Counterparty sync started in thread tenant_id=%s", tenant_id)
    return True


def maybe_schedule_tenant_data_sync(
    db: Session,
    tenant_id: int,
    period: Optional[str] = None,
) -> None:
    """Поставить в очередь sync платежей + контрагентов, если кэш устарел или пуст."""
    period = period or current_period()
    row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    if row and row.status == "running":
        return
    if row and row.data and not _cache_is_stale(row):
        return

    from app.services.tenant_data_sync import request_tenant_data_sync

    request_tenant_data_sync(db, tenant_id, period)


def schedule_all_active_tenants_sync(period: Optional[str] = None) -> int:
    from app.db.database import SessionLocal
    from app.models.catalog import Tenant
    from app.services.tenant_1c import tenant_has_1c_credentials
    from app.services.tenant_data_sync import request_tenant_data_sync

    period = period or current_period()
    db = SessionLocal()
    scheduled = 0
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).all()
        for tenant in tenants:
            if not tenant_has_1c_credentials(tenant):
                continue
            try:
                request_tenant_data_sync(db, tenant.id, period)
                scheduled += 1
            except Exception as exc:
                logger.warning("Could not schedule sync tenant_id=%s: %s", tenant.id, exc)
        return scheduled
    finally:
        db.close()
