"""Сопоставление счетов tenant_payments с контрагентами (COM без UUID в batch)."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

VIRTUAL_PREFIX = "virtual:"

# Допуск при сопоставлении сумм COM batch ↔ tenant_payments (округление в 1С).
AMOUNT_MATCH_TOLERANCE = 2.0


def amounts_near(
    left: Optional[float],
    right: Optional[float],
    tolerance: float = AMOUNT_MATCH_TOLERANCE,
) -> bool:
    if left is None or right is None:
        return False
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def normalize_counterparty_name(value: Optional[str]) -> str:
    return " ".join(str(value or "").lower().split())


def name_match_variants(value: Optional[str]) -> list[str]:
    """Варианты имени для поиска в справочнике (без неоднозначных подстановок)."""
    base = normalize_counterparty_name(value)
    if not base:
        return []

    variants: list[str] = []
    for candidate in (base,):
        if candidate and candidate not in variants:
            variants.append(candidate)

    no_paren = re.sub(r"\([^)]*\)", " ", base)
    no_paren = " ".join(no_paren.split())
    if no_paren and no_paren not in variants:
        variants.append(no_paren)

    no_ip = re.sub(r"\bип\b\.?", " ", no_paren or base)
    no_ip = " ".join(no_ip.split())
    if no_ip and no_ip not in variants:
        variants.append(no_ip)

    return variants


def build_name_resolution_index(
    cache_data: list[dict[str, Any]],
) -> dict[str, str]:
    """variant нормализованного имени → cp_id (только однозначные совпадения)."""
    hits: dict[str, list[str]] = {}
    for cp in cache_data:
        cp_id = (cp.get("id") or "").strip().lower()
        if not cp_id:
            continue
        for variant in name_match_variants(cp.get("fullName")):
            hits.setdefault(variant, []).append(cp_id)

    index: dict[str, str] = {}
    for variant, cp_ids in hits.items():
        unique = list(dict.fromkeys(cp_ids))
        if len(unique) == 1:
            index[variant] = unique[0]
    return index


def resolve_to_cache_counterparty_id(
    tenant_name: Optional[str],
    name_index: dict[str, str],
) -> Optional[str]:
    """UUID контрагента из кэша по имени — только при однозначном совпадении."""
    for variant in name_match_variants(tenant_name):
        cp_id = name_index.get(variant)
        if cp_id:
            return cp_id

    normalized = normalize_counterparty_name(tenant_name)
    if not normalized:
        return None

    token_hits: list[str] = []
    tokens = [t for t in re.split(r"[^\wа-яё]+", normalized) if len(t) >= 4]
    if not tokens:
        return None
    for variant, cp_id in name_index.items():
        if all(token in variant for token in tokens):
            token_hits.append(cp_id)
    unique = list(dict.fromkeys(token_hits))
    if len(unique) == 1:
        return unique[0]
    return None


def virtual_counterparty_key(display_name: str) -> str:
    normalized = normalize_counterparty_name(display_name)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{VIRTUAL_PREFIX}{digest}"


def is_virtual_counterparty_id(cp_key: Optional[str]) -> bool:
    return str(cp_key or "").startswith(VIRTUAL_PREFIX)


def resolve_payment_counterparty_key(
    *,
    counterparty_id: Optional[str],
    tenant_name: Optional[str],
    name_index: dict[str, str],
    cache_names_by_id: Optional[dict[str, str]] = None,
    bin_index: Optional[dict[str, str]] = None,
    bin_value: Optional[str] = None,
) -> tuple[str, str]:
    """Ключ группировки (UUID или virtual:…) и отображаемое имя.

    Порядок приоритета — id > БИН > имя — тот же, что уже в
    bind_invoice_to_counterparty (1С-путь, payment_service.sync_from_1c);
    этой функции он не переиспользует напрямую, потому что здесь нужен
    virtual:-фолбэк, которого там нет. bin_index/bin_value — по умолчанию
    None, БИН-матчинг просто не участвует (существующие вызовы и парсеры,
    что не заполняют RawChargeRow.bin_value, ведут себя как раньше)."""
    cache_names_by_id = cache_names_by_id or {}
    bin_index = bin_index or {}
    cp_id = (counterparty_id or "").strip().lower()
    name = (tenant_name or "").strip()

    if cp_id:
        display = name or cache_names_by_id.get(cp_id, "")
        return cp_id, display or cp_id

    bin_key = str(bin_value or "").strip()
    if bin_key and bin_key in bin_index:
        matched = bin_index[bin_key]
        display = cache_names_by_id.get(matched, name)
        return matched, display or name

    matched = resolve_to_cache_counterparty_id(name, name_index)
    if matched:
        display = cache_names_by_id.get(matched, name)
        return matched, display or name

    if name:
        return virtual_counterparty_key(name), name

    return "", ""


def build_bin_resolution_index(
    cache_data: list[dict[str, Any]],
) -> dict[str, str]:
    """БИН/ИИН - cp_id (только однозначные совпадения)."""
    hits: dict[str, list[str]] = {}
    for cp in cache_data:
        cp_id = (cp.get("id") or "").strip().lower()
        if not cp_id:
            continue
        for key in ("bin", "iin", "BIN", "IIN"):
            raw = str(cp.get(key) or "").strip()
            if not raw:
                continue
            hits.setdefault(raw, []).append(cp_id)
    index: dict[str, str] = {}
    for bin_key, cp_ids in hits.items():
        unique = list(dict.fromkeys(cp_ids))
        if len(unique) == 1:
            index[bin_key] = unique[0]
    return index


def load_cache_name_maps(
    cache_data: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    """name_index + cp_id → fullName."""
    name_index = build_name_resolution_index(cache_data)
    names_by_id: dict[str, str] = {}
    for cp in cache_data:
        cp_id = (cp.get("id") or "").strip().lower()
        full_name = (cp.get("fullName") or "").strip()
        if cp_id and full_name:
            names_by_id[cp_id] = full_name
    return name_index, names_by_id


def bind_invoice_to_counterparty(
    *,
    counterparty_id: Optional[str],
    tenant_name: Optional[str],
    name_index: dict[str, str],
    names_by_id: dict[str, str],
    bin_index: Optional[dict[str, str]] = None,
    bin_value: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """
    Привязка счёта к контрагенту: сначала id из 1С, затем БИН, затем имя.
    Возвращает (cp_id|None, display_name).
    """
    bin_index = bin_index or {}
    cp_id = (counterparty_id or "").strip().lower()
    name = (tenant_name or "").strip()

    if cp_id:
        display = names_by_id.get(cp_id) or name or cp_id
        return cp_id, display

    bin_key = str(bin_value or "").strip()
    if bin_key and bin_key in bin_index:
        matched = bin_index[bin_key]
        display = names_by_id.get(matched) or name or matched
        return matched, display

    matched = resolve_to_cache_counterparty_id(name, name_index)
    if matched:
        display = names_by_id.get(matched) or name or matched
        return matched, display

    return None, name
