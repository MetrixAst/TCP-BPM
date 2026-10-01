"""Привязка контрагентов к папкам 1С: parent → folderName (fullName группы).

Не меняет скрипты Nova и не фильтрует выдачу — только дополняет поля.
Nova op=counterparties не отдаёт Родитель; для Nova-org с OData URL
берём Parent_Key через OData side-channel (логин/пароль арендатора).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.client_1c.models import Counterparty
from app.services.odata_1c_client import OData1CClient, is_odata_url, _first_str
from app.services.tenant_1c import tenant_uses_nova_org

logger = logging.getLogger(__name__)

_ZERO = "00000000-0000-0000-0000-000000000000"


def _is_empty_guid(value: str) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return True
    return raw.replace("-", "") == "0" * 32 or raw == _ZERO


def _resolve_odata_sidechannel(tenant) -> Optional[tuple[str, str, str]]:
    """(odata_url, login, password) или None."""
    if not tenant:
        return None
    login = (getattr(tenant, "one_c_login", None) or "").strip()
    password = (getattr(tenant, "one_c_password", None) or "").strip()
    if not login or not password:
        return None

    base = (getattr(tenant, "one_c_base_url", None) or "").strip()
    if base and is_odata_url(base):
        return base, login, password

    org_id = getattr(tenant, "nova_organization_id", None)
    if not org_id:
        return None
    try:
        from app.services.nova_1c_service import get_nova_1c_service

        cfg = get_nova_1c_service().get_org_config(int(org_id))
        odata_url = (cfg.odata_url or "").strip()
        if odata_url and is_odata_url(odata_url):
            return odata_url, login, password
    except Exception as exc:
        logger.debug("OData side-channel: org config unavailable: %s", exc)
    return None


def _odata_parent_and_folder_maps(
    odata_url: str,
    login: str,
    password: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """cp_id → parent_id; folder_id → folder fullName."""
    client = OData1CClient(
        base_url=odata_url,
        api_user=login,
        api_password=password,
        timeout=(10, 120),
    )
    try:
        entity = "Catalog_Контрагенты"
        if client._counterparty_entities:
            entity = client._counterparty_entities[0]
        rows = client._fetch_entity_rows(
            entity,
            {"$format": "json"},
            max_rows=50000,
        )
        parent_by_cp: dict[str, str] = {}
        folder_names: dict[str, str] = {}
        for row in rows:
            ref = _first_str(row, "Ref_Key", "Ref", "Key", "id").lower()
            if not ref:
                continue
            name = _first_str(
                row,
                "НаименованиеПолное",
                "Description",
                "Наименование",
                "FullName",
                "fullName",
            )
            if row.get("IsFolder"):
                if name:
                    folder_names[ref] = name.strip()
                continue
            parent = _first_str(
                row, "Parent_Key", "Parent", "Родитель_Key", "Родитель"
            ).lower()
            if parent and not _is_empty_guid(parent):
                parent_by_cp[ref] = parent
        return parent_by_cp, folder_names
    finally:
        try:
            client.close()
        except Exception:
            pass


def _groups_from_nova_client(client: Any) -> dict[str, str]:
    """folder_id → fullName из counterparty_groups."""
    if not client or not hasattr(client, "get_counterparty_groups"):
        return {}
    try:
        groups = client.get_counterparty_groups() or []
    except Exception as exc:
        logger.debug("Nova counterparty_groups unavailable: %s", exc)
        return {}
    out: dict[str, str] = {}
    for group in groups:
        gid = str(group.get("id") or "").strip().lower()
        name = str(group.get("fullName") or "").strip()
        if gid and name:
            out[gid] = name
    return out


def enrich_counterparties_with_folders(
    counterparties: list[Counterparty],
    *,
    tenant=None,
    nova_client: Any = None,
) -> int:
    """
    Заполняет Counterparty.parent и folder_name.
    Возвращает число контрагентов с непустым folder_name после обогащения.
    """
    if not counterparties:
        return 0

    folder_names = _groups_from_nova_client(nova_client)
    parent_by_cp: dict[str, str] = {}

    # Уже заполненные parent из клиента (OData get_counterparties).
    for cp in counterparties:
        cp_id = (cp.id or "").strip().lower()
        parent = (getattr(cp, "parent", None) or "").strip().lower()
        if cp_id and parent and not _is_empty_guid(parent):
            parent_by_cp[cp_id] = parent
        name = (getattr(cp, "folder_name", None) or "").strip()
        if parent and name and parent not in folder_names:
            folder_names[parent] = name

    # Nova scripts не отдают Родитель — OData side-channel, если есть URL+пароль.
    if not parent_by_cp and tenant and tenant_uses_nova_org(tenant):
        side = _resolve_odata_sidechannel(tenant)
        if side:
            odata_url, login, password = side
            try:
                odata_parents, odata_folders = _odata_parent_and_folder_maps(
                    odata_url, login, password
                )
                parent_by_cp.update(odata_parents)
                for fid, fname in odata_folders.items():
                    folder_names.setdefault(fid, fname)
                logger.info(
                    "Folder enrich OData: parents=%s folders=%s tenant_id=%s",
                    len(odata_parents),
                    len(odata_folders),
                    getattr(tenant, "id", None),
                )
            except Exception as exc:
                logger.warning(
                    "Folder enrich OData failed tenant_id=%s: %s",
                    getattr(tenant, "id", None),
                    exc,
                )

    filled = 0
    for cp in counterparties:
        cp_id = (cp.id or "").strip().lower()
        parent = (getattr(cp, "parent", None) or "").strip()
        if (not parent or _is_empty_guid(parent)) and cp_id in parent_by_cp:
            parent = parent_by_cp[cp_id]
            cp.parent = parent
        if not parent or _is_empty_guid(parent):
            continue
        name = (getattr(cp, "folder_name", None) or "").strip()
        if not name:
            name = folder_names.get(parent.lower(), "")
            if name:
                cp.folder_name = name
        if (cp.folder_name or "").strip():
            filled += 1

    logger.info(
        "Folder enrich done: %s/%s with folderName tenant_id=%s",
        filled,
        len(counterparties),
        getattr(tenant, "id", None),
    )
    return filled


def folders_payload_from_counterparties(
    counterparties: list[Counterparty],
    *,
    extra_groups: Optional[list[dict]] = None,
) -> list[dict[str, str]]:
    """Уникальные папки для API: id + fullName."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for cp in counterparties:
        name = (getattr(cp, "folder_name", None) or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": (getattr(cp, "parent", None) or "").strip(),
                "fullName": name,
            }
        )
    for group in extra_groups or []:
        name = str(group.get("fullName") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": str(group.get("id") or "").strip(),
                "fullName": name,
            }
        )
    out.sort(key=lambda f: f["fullName"].casefold())
    return out
