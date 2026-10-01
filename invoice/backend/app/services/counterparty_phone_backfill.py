"""Backfill телефонов из counterparty_phones → 1С (OData / City Mall)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.catalog import CounterpartyPhone, Tenant
from app.services.counterparty_contact_sync import (
    refresh_counterparties_after_phone_write,
    sync_counterparty_phone_field_to_1c,
)
from app.services.phone_list import split_phone_values
from app.services.tenant_1c import get_integration_for_tenant

logger = logging.getLogger(__name__)


def _client_supports_phone_write(integration) -> bool:
    client = getattr(integration, "client", None)
    if not client:
        return False
    if getattr(integration, "_uses_odata", False) or type(client).__name__ == "OData1CClient":
        return True
    if type(client).__name__ == "NovaBuh1CClient":
        ensure = getattr(client, "_ensure_agent_id", None)
        if callable(ensure):
            try:
                ensure()
            except Exception as exc:
                logger.debug("Nova agent lookup for backfill: %s", exc)
        return bool(getattr(client, "_odata_org", False))
    return False


def backfill_counterparty_phones_to_1c(
    db: Session,
    *,
    tenant_id: int,
    trc_id: Optional[int] = None,
    dry_run: bool = False,
    limit: int = 0,
    after_id: int = 0,
) -> dict[str, Any]:
    """
    Выгрузить телефоны из БД платформы в 1С и при успехе обновить кэш контрагентов.

    Возвращает сводку для API/скрипта. Не удаляет данные.
    Для обхода ingress timeout: limit + after_id (пачки по id).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        return {
            "ok": False,
            "error": f"tenant_id={tenant_id} не найден",
            "dry_run": dry_run,
            "total": 0,
            "ok_count": 0,
            "fail_count": 0,
            "empty_skip": 0,
            "last_processed_id": None,
            "items": [],
        }
    if trc_id is not None and tenant.trc_id != trc_id:
        return {
            "ok": False,
            "error": f"tenant_id={tenant_id} не принадлежит trc_id={trc_id}",
            "dry_run": dry_run,
            "total": 0,
            "ok_count": 0,
            "fail_count": 0,
            "empty_skip": 0,
            "last_processed_id": None,
            "items": [],
        }

    query = (
        db.query(CounterpartyPhone)
        .filter(CounterpartyPhone.trc_id == tenant.trc_id)
        .order_by(CounterpartyPhone.id)
    )
    if after_id and after_id > 0:
        query = query.filter(CounterpartyPhone.id > after_id)
    if limit and limit > 0:
        rows = query.limit(limit).all()
    else:
        rows = query.all()

    summary: dict[str, Any] = {
        "ok": True,
        "error": None,
        "dry_run": dry_run,
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "trc_id": tenant.trc_id,
        "total": len(rows),
        "ok_count": 0,
        "fail_count": 0,
        "empty_skip": 0,
        "cache_refreshed": False,
        "last_processed_id": rows[-1].id if rows else after_id or None,
        "items": [],
    }

    if not rows:
        return summary

    # Проверка транспорта: прямой OData или Nova OData (City Mall). COM (Maxi) — нет.
    integration = get_integration_for_tenant(db, tenant.id)
    if not integration.client:
        summary["ok"] = False
        summary["error"] = f"1С клиент недоступен: {integration.last_error}"
        return summary
    if not _client_supports_phone_write(integration):
        summary["ok"] = False
        summary["error"] = (
            f"tenant {tenant.id} ({tenant.name}): запись телефонов только для "
            "OData / Nova OData (City Mall), не для COM (Maxi)"
        )
        return summary

    if dry_run:
        for row in rows:
            phones = split_phone_values(row.phone)
            summary["items"].append(
                {
                    "one_c_counterparty_id": row.one_c_counterparty_id,
                    "counterparty_name": row.counterparty_name,
                    "phones": phones,
                    "status": "would_write" if phones else "empty_skip",
                }
            )
            if not phones:
                summary["empty_skip"] += 1
            else:
                summary["ok_count"] += 1
        if hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass
        return summary

    try:
        for row in rows:
            phones = split_phone_values(row.phone)
            if not phones:
                summary["empty_skip"] += 1
                summary["items"].append(
                    {
                        "one_c_counterparty_id": row.one_c_counterparty_id,
                        "counterparty_name": row.counterparty_name,
                        "phones": [],
                        "status": "empty_skip",
                    }
                )
                continue
            result = sync_counterparty_phone_field_to_1c(
                integration,
                row.one_c_counterparty_id,
                row.phone or "",
            )
            if result.get("ok"):
                summary["ok_count"] += 1
                summary["items"].append(
                    {
                        "one_c_counterparty_id": row.one_c_counterparty_id,
                        "counterparty_name": row.counterparty_name,
                        "phones": phones,
                        "status": "ok",
                        "written": result.get("written"),
                        "skipped": result.get("skipped"),
                    }
                )
            else:
                summary["fail_count"] += 1
                summary["ok"] = False
                msg = "; ".join(result.get("messages") or []) or "ошибка записи в 1С"
                summary["items"].append(
                    {
                        "one_c_counterparty_id": row.one_c_counterparty_id,
                        "counterparty_name": row.counterparty_name,
                        "phones": phones,
                        "status": "fail",
                        "message": msg,
                    }
                )
                logger.warning(
                    "backfill phone fail tenant=%s cp=%s: %s",
                    tenant.id,
                    row.one_c_counterparty_id,
                    msg,
                )
    finally:
        if hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass

    if summary["ok_count"]:
        refresh_counterparties_after_phone_write(db, tenant.id)
        summary["cache_refreshed"] = True

    return summary
