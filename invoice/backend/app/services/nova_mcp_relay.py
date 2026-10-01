"""MCP relay client: onec.buh.getpdf (OData) and onec.com.runScript (COM PDF)."""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_COM_GETPDF_UNAVAILABLE = "plugin-onec' not available"

PRINT_FORM_STEP = {
    "id": "pdf",
    "op": "print_form",
    "ref": "$ref",
    "handler": "fsapi",
    "method": "СчетНаОплату",
    "layout": "СчетЗаказ",
    "format": "pdf",
}


class NovaMcpRelayError(Exception):
    pass


def relay_configured() -> bool:
    return bool(
        (settings.NOVA_MCP_RELAY_URL or "").strip()
        and (settings.NOVA_MCP_RELAY_API_KEY or "").strip()
    )


def _normalize_uid(invoice_uid: str) -> str:
    uid = (invoice_uid or "").strip()
    if uid.startswith("@uuid:"):
        uid = uid[6:].strip()
    return uid


def _relay_headers(org_api_key: Optional[str] = None) -> dict[str, str]:
    relay_key = (settings.NOVA_MCP_RELAY_API_KEY or "").strip()
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": relay_key,
    }
    if org_api_key:
        headers["X-Org-Key"] = org_api_key.strip()
    return headers


def call_relay_tool(
    *,
    agent_id: str,
    tool: str,
    arguments: dict,
    org_api_key: Optional[str] = None,
    timeout: int = 180,
) -> dict:
    relay_url = (settings.NOVA_MCP_RELAY_URL or "").rstrip("/")
    if not relay_url or not (settings.NOVA_MCP_RELAY_API_KEY or "").strip():
        raise NovaMcpRelayError(
            "Nova MCP relay не настроен (NOVA_MCP_RELAY_URL / NOVA_MCP_RELAY_API_KEY)"
        )
    if not agent_id:
        raise NovaMcpRelayError("agent_id не задан для организации Nova")

    url = f"{relay_url}/api/v1/agents/{agent_id}/tools/{tool}"
    try:
        response = requests.post(
            url,
            json={"arguments": arguments},
            headers=_relay_headers(org_api_key),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise NovaMcpRelayError(f"MCP relay request failed: {exc}") from exc

    if response.status_code != 200:
        raise NovaMcpRelayError(
            f"MCP {tool} HTTP {response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise NovaMcpRelayError(f"MCP {tool} returned non-JSON response") from exc

    if payload.get("success") is False:
        err = payload.get("error") or "unknown relay error"
        raise NovaMcpRelayError(f"MCP {tool}: {err}")

    return payload


def _extract_blob_base64(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    blob = payload.get("blob")
    if isinstance(blob, dict):
        raw = blob.get("base64") or blob.get("pdf_base64") or blob.get("data")
        if raw and str(raw).strip():
            return str(raw).strip()

    results = payload.get("results")
    if isinstance(results, dict):
        found = _extract_blob_base64(results)
        if found:
            return found

    result = payload.get("result")
    if isinstance(result, dict):
        found = _extract_blob_base64(result)
        if found:
            return found

    for key in ("base64", "pdf_base64", "file_base64", "data"):
        raw = payload.get(key)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


def is_com_getpdf_unavailable(exc: BaseException) -> bool:
    return _COM_GETPDF_UNAVAILABLE in str(exc)


def build_com_pdf_script_body(source_body: dict, *, uid: str) -> dict:
    """COM recipe: ref → batch → print_form → pdf_base64 in results.pdf."""
    body = copy.deepcopy(source_body)
    steps = list(body.get("steps") or [])
    steps = [step for step in steps if step.get("id") not in {"pdf", "org", "obj"}]
    if not any(step.get("id") == "ref" for step in steps):
        steps.insert(
            0,
            {
                "id": "ref",
                "op": "com_call",
                "args": ["$uid"],
                "path": "Документы.СчетНаОплатуПокупателю",
                "method": "ПолучитьСсылку",
            },
        )
    if not any(step.get("id") == "pdf" for step in steps):
        steps.append(dict(PRINT_FORM_STEP))
    body["steps"] = steps
    body["return"] = ["pdf"]
    uid_norm = _normalize_uid(uid)
    body["vars"] = {"uid": f"@uuid:{uid_norm}"}
    return body


def call_buh_contacts_set(
    *,
    agent_id: str,
    object_id: str,
    value: str,
    vid: str,
    contact_type: str = "Телефон",
    org_api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    OData agents: onec.buh.contacts_set — upsert телефона в регистре контактной информации.

    Postman: arguments.item = { object, vid, type, value }
    → result.results.processed.items[0] с ok/action (create|update).
    """
    object_guid = _normalize_uid(object_id)
    if not object_guid or not (value or "").strip() or not (vid or "").strip():
        raise NovaMcpRelayError("contacts_set: нужны object, vid и value")

    payload = call_relay_tool(
        agent_id=agent_id,
        tool="onec.buh.contacts_set",
        arguments={
            "item": {
                "object": object_guid,
                "vid": vid.strip(),
                "type": contact_type or "Телефон",
                "value": value.strip(),
            }
        },
        org_api_key=org_api_key,
        timeout=120,
    )

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise NovaMcpRelayError("MCP contacts_set: пустой result")
    if result.get("ok") is False and not (
        isinstance(result.get("results"), dict)
        and (result.get("results") or {}).get("processed")
    ):
        err = result.get("error") or payload.get("error") or "contacts_set failed"
        raise NovaMcpRelayError(f"MCP contacts_set: {err}")

    results = result.get("results") if isinstance(result.get("results"), dict) else {}
    processed = results.get("processed") if isinstance(results, dict) else None
    items = []
    if isinstance(processed, dict):
        items = processed.get("items") or []
    if not items:
        raise NovaMcpRelayError(
            f"MCP contacts_set: нет processed.items (keys={list(payload.keys())})"
        )
    item = items[0] if isinstance(items[0], dict) else {}
    return {
        "ok": bool(item.get("ok", True)),
        "action": str(item.get("action") or ""),
        "message": str(item.get("message") or item.get("error") or ""),
        "raw": item,
    }


def call_buh_getpdf(
    *,
    agent_id: str,
    invoice_uid: str,
    org_api_key: Optional[str] = None,
) -> Optional[str]:
    """
    OData agents: relay tool onec.buh.getpdf → result.results.blob.base64.
    """
    uid = _normalize_uid(invoice_uid)
    payload = call_relay_tool(
        agent_id=agent_id,
        tool="onec.buh.getpdf",
        arguments={"uid": uid},
        org_api_key=org_api_key,
    )

    base64_pdf = _extract_blob_base64(payload)
    if base64_pdf:
        return base64_pdf

    result = payload.get("result") or {}
    if result.get("ok") is False:
        err = payload.get("error") or result.get("error")
        raise NovaMcpRelayError(f"MCP getpdf failed: {err}")

    inner = result.get("results") if isinstance(result, dict) else None
    base64_pdf = _extract_blob_base64(inner or {})
    if base64_pdf:
        return base64_pdf

    logger.warning("MCP getpdf: no blob.base64 in response keys=%s", list(payload.keys()))
    return None


def call_com_invoice_pdf(
    *,
    agent_id: str,
    invoice_uid: str,
    script_body: dict,
    org_api_key: Optional[str] = None,
) -> dict:
    """COM agents: onec.com.runScript with print_form step."""
    arguments = build_com_pdf_script_body(script_body, uid=invoice_uid)
    payload = call_relay_tool(
        agent_id=agent_id,
        tool="onec.com.runScript",
        arguments=arguments,
        org_api_key=org_api_key,
    )
    result = payload.get("result") or {}
    if result.get("ok") is False:
        err = result.get("error") or payload.get("error")
        raise NovaMcpRelayError(f"COM runScript PDF: {err}")
    return result
