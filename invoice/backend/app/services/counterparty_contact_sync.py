"""Синхронизация телефонов контрагента из invoice в 1С (регистр контактной информации)."""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from app.services.integration_1c import Integration1C
from app.services.phone_list import split_phone_values

logger = logging.getLogger(__name__)


def _normalize_upsert_result(result: Any) -> dict[str, Any]:
    """OData возвращает dict; Nova/COM historically — False."""
    if isinstance(result, dict):
        return {
            "ok": bool(result.get("ok")),
            "action": str(result.get("action") or ""),
            "message": str(result.get("message") or ""),
        }
    if result is True:
        return {"ok": True, "action": "create", "message": ""}
    return {
        "ok": False,
        "action": "skip",
        "message": "Запись телефона в 1С для этого подключения не поддерживается",
    }


def sync_counterparty_phones_to_1c(
    integration: Optional[Integration1C],
    counterparty_id: str,
    phones: Iterable[str],
) -> dict[str, Any]:
    """
    Сохранить номера в 1С (OData City Mall и аналоги).

    Запись в нашей БД вызывающий код делает отдельно.
    Возвращает сводку: ok / written / skipped / failed / supported / messages.
    """
    summary: dict[str, Any] = {
        "ok": True,
        "supported": False,
        "written": 0,
        "skipped": 0,
        "failed": [],
        "actions": [],
        "messages": [],
    }
    client = integration.client if integration else None
    if not client or not hasattr(client, "upsert_counterparty_phone"):
        summary["ok"] = False
        summary["messages"].append("Клиент 1С недоступен для записи телефона")
        return summary

    cp_id = (counterparty_id or "").strip()
    if not cp_id:
        summary["ok"] = False
        summary["messages"].append("Не указан контрагент")
        return summary

    unique: list[str] = []
    for raw in phones:
        phone = (raw or "").strip()
        if phone and phone not in unique:
            unique.append(phone)
    if not unique:
        return summary

    # OData direct или Nova OData-org (City Mall через onec.buh.contacts_set).
    # COM (Maxi) — не supported.
    uses_odata = bool(getattr(integration, "_uses_odata", False)) or type(
        client
    ).__name__ == "OData1CClient"
    if not uses_odata and type(client).__name__ == "NovaBuh1CClient":
        ensure = getattr(client, "_ensure_agent_id", None)
        if callable(ensure):
            try:
                ensure()
            except Exception as exc:
                logger.debug("Nova agent lookup for phone sync: %s", exc)
        uses_odata = bool(getattr(client, "_odata_org", False))
    summary["supported"] = uses_odata

    kinds = list(getattr(client, "PHONE_CONTACT_KINDS", ()))
    for index, phone in enumerate(unique):
        kind_vid = kinds[index] if index < len(kinds) else None
        try:
            raw_result = client.upsert_counterparty_phone(
                cp_id,
                phone,
                kind_vid=kind_vid,
            )
            result = _normalize_upsert_result(raw_result)
        except Exception as exc:
            logger.warning(
                "1C phone sync error cp=%s phone=%s: %s",
                cp_id,
                phone,
                exc,
            )
            summary["ok"] = False
            summary["failed"].append({"phone": phone, "message": str(exc)})
            summary["messages"].append(f"{phone}: {exc}")
            continue

        action = result.get("action") or ""
        summary["actions"].append({"phone": phone, **result})
        if result.get("ok"):
            if action in ("create", "update"):
                summary["written"] += 1
                logger.info(
                    "1C phone sync ok cp=%s phone=%s action=%s",
                    cp_id,
                    phone,
                    action,
                )
            else:
                summary["skipped"] += 1
                logger.info(
                    "1C phone sync skip cp=%s phone=%s: %s",
                    cp_id,
                    phone,
                    result.get("message") or action,
                )
            continue

        summary["ok"] = False
        msg = result.get("message") or "1С отклонила сохранение телефона"
        summary["failed"].append({"phone": phone, "message": msg, "action": action})
        summary["messages"].append(f"{phone}: {msg}")
        logger.warning(
            "1C phone sync failed cp=%s phone=%s action=%s: %s",
            cp_id,
            phone,
            action,
            msg,
        )

    return summary


def sync_counterparty_phone_field_to_1c(
    integration: Optional[Integration1C],
    counterparty_id: str,
    phone_field: str,
) -> dict[str, Any]:
    return sync_counterparty_phones_to_1c(
        integration,
        counterparty_id,
        split_phone_values(phone_field),
    )


def refresh_counterparties_after_phone_write(db, tenant_id: int) -> None:
    """Обновить кэш контрагентов, чтобы phoneNumber появился в реестре."""
    try:
        from app.services.counterparty_cache_service import request_counterparty_cache_sync

        started = request_counterparty_cache_sync(db, tenant_id)
        logger.info(
            "Counterparty cache sync after phone write tenant_id=%s started=%s",
            tenant_id,
            started,
        )
    except Exception as exc:
        logger.warning(
            "Counterparty cache sync after phone write failed tenant_id=%s: %s",
            tenant_id,
            exc,
        )
