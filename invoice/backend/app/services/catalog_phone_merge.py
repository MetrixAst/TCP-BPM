from __future__ import annotations

import logging
import re
from typing import List, Optional, Set, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.catalog import CounterpartyPhone, Tenant
from app.services.tenant_1c import get_tenant_by_id


def _norm_tax_id(value: Optional[str]) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def _tenant_tax_ids(tenant: Tenant) -> Set[str]:
    ids: Set[str] = set()
    for field in (tenant.bin_value, tenant.iin_value):
        n = _norm_tax_id(field)
        if len(n) >= 10:
            ids.add(n)
    return ids


def _cp_tax_ids(cp: dict) -> Set[str]:
    ids: Set[str] = set()
    for field in (cp.get("bin"), cp.get("iin"), cp.get("rnn")):
        n = _norm_tax_id(field)
        if len(n) >= 10:
            ids.add(n)
    return ids


def _name_match(hint: str, full_name: str) -> bool:
    h = (hint or "").strip().lower()
    if len(h) < 2:
        return False
    return h in (full_name or "").lower()


def merge_catalog_tenant_phones(
    db: Session, tenant_id: Optional[int], result: List[dict]
) -> Tuple[int, Optional[str]]:
    """
    Заполняет phoneNumber из каталога арендаторов.
    Совпадение: ID контрагента 1С, нормализованный БИН/ИИН, фрагмент названия в 1С.
    """
    selected = get_tenant_by_id(db, tenant_id)
    if not selected:
        return 0, None

    catalog_tenants = (
        db.query(Tenant)
        .filter(Tenant.trc_id == selected.trc_id, Tenant.is_active.is_(True))
        .all()
    )

    by_tax: dict[str, str] = {}
    by_cp_id: dict[str, str] = {}
    contact_by_cp_id: dict[str, str] = {}
    name_rules: list[tuple[str, str]] = []

    for row in (
        db.query(CounterpartyPhone).filter(CounterpartyPhone.trc_id == selected.trc_id).all()
    ):
        phone = (row.phone or "").strip()
        if not phone:
            continue
        key = (row.one_c_counterparty_id or "").strip().lower()
        if key:
            by_cp_id[key] = phone
            if row.contact_name:
                contact_by_cp_id[key] = row.contact_name.strip()

    for t in catalog_tenants:
        phone = (t.phone or "").strip()
        if not phone:
            continue
        cp_id = (t.one_c_counterparty_id or "").strip().lower()
        if cp_id:
            by_cp_id[cp_id] = phone
        for tid in _tenant_tax_ids(t):
            by_tax[tid] = phone
        hint = (t.one_c_name_match or "").strip()
        if hint:
            name_rules.append((hint.lower(), phone))

    merged = 0
    selected_linked = False

    for cp in result:
        cp_id = (cp.get("id") or "").strip().lower()
        full_name = cp.get("fullName") or ""
        if cp_id in contact_by_cp_id and not cp.get("contactPerson"):
            cp["contactPerson"] = contact_by_cp_id[cp_id]

        if cp.get("phoneNumber"):
            if selected and _cp_linked_to_tenant(cp, selected):
                selected_linked = True
            continue

        phone = by_cp_id.get(cp_id)

        if not phone:
            for tid in _cp_tax_ids(cp):
                phone = by_tax.get(tid)
                if phone:
                    break

        if not phone:
            for hint, p in name_rules:
                if _name_match(hint, full_name):
                    phone = p
                    break

        if phone:
            cp["phoneNumber"] = phone
            cp["phoneFromCatalog"] = True
            merged += 1
            if selected and _cp_linked_to_tenant(cp, selected):
                selected_linked = True

    stored_cp_phones = (
        db.query(CounterpartyPhone)
        .filter(CounterpartyPhone.trc_id == selected.trc_id)
        .count()
    )
    warning: Optional[str] = None
    if result and not any(cp.get("phoneNumber") for cp in result):
        warning = (
            "Телефоны из вкладки «Контакты» в 1С не передаются через OData. "
            "Укажите номера получателей в админке: «Телефоны контрагентов для WhatsApp»."
        )
    elif result and stored_cp_phones == 0:
        warning = (
            "Для рассылки укажите телефоны получателей в админке "
            "(раздел «Телефоны контрагентов для WhatsApp»). "
            "1С не отдаёт телефоны из карточки контрагента."
        )
    selected_phone = (selected.phone or "").strip()
    if selected_phone and not selected_linked:
        sample_bin = ""
        hint = (selected.one_c_name_match or "").strip()
        if hint:
            for cp in result:
                if _name_match(hint, cp.get("fullName") or ""):
                    sample_bin = cp.get("bin") or cp.get("iin") or ""
                    break
        admin_ids = ", ".join(sorted(_tenant_tax_ids(selected))) or "не указан"
        parts = [
            f"Телефон арендатора «{selected.name}» ({selected_phone}) не привязан к строке в таблице 1С.",
            f"БИН/ИИН в админке: {admin_ids}.",
        ]
        if sample_bin:
            parts.append(f"В 1С по фрагменту «{hint}» найден БИН/ИИН: {sample_bin}.")
        elif hint:
            parts.append(f"По фрагменту «{hint}» контрагент в 1С не найден.")
        else:
            parts.append(
                "Укажите в админке правильный БИН из 1С, фрагмент названия (например MOON) "
                "или ID контрагента 1С."
            )
        warning = " ".join(parts)

    if merged:
        logger.debug(f" Merged {merged} phone(s) from catalog tenants (admin panel)")
    return merged, warning


def _cp_linked_to_tenant(cp: dict, tenant: Tenant) -> bool:
    phone = (tenant.phone or "").strip()
    if not phone or cp.get("phoneNumber") != phone:
        return False
    cp_id = (cp.get("id") or "").strip().lower()
    link_id = (tenant.one_c_counterparty_id or "").strip().lower()
    if link_id and cp_id == link_id:
        return True
    if _tenant_tax_ids(tenant) & _cp_tax_ids(cp):
        return True
    hint = (tenant.one_c_name_match or "").strip()
    if hint and _name_match(hint, cp.get("fullName") or ""):
        return True
    return False
