"""1C client via Nova buh scripts (COM/MCP and OData-routed orgs)."""

from __future__ import annotations

import base64
import binascii
import calendar
import json
import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

from app.core.config import settings
from app.client_1c.models import AuthResponse, Counterparty, Invoice
from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.services.counterparty_name_match import normalize_counterparty_name
from app.services.nova_1c_service import Nova1CService, Nova1CServiceError, get_nova_1c_service
from app.services.nova_com_pdf_enrichment import (
    enrichment_from_script_results,
    fetch_com_pdf_enrichment,
)
from app.services.nova_query_results import query_step_first_row, query_step_to_dicts
from app.services.invoice_service_type import (
    DEFAULT_KNP_BY_SERVICE_TYPE,
    due_date_in_invoice_month,
    due_day_for_service_type,
    resolve_invoice_service_types,
)
from app.services.nova_mcp_relay import (
    NovaMcpRelayError,
    call_buh_contacts_set,
    call_buh_getpdf,
    relay_configured,
)
from app.services.payment_status_rules import paid_enough, payment_coverage_status
from app.services.safe_filename import safe_filename_component

logger = logging.getLogger(__name__)

_EMPTY_INVOICE_GUID = "00000000-0000-0000-0000-000000000000"
_PDF_CACHE_MAX_AGE = timedelta(days=7)
# бамп: аренда теперь показывает СЛЕДУЮЩИЙ месяц («за Сентябрь», не «за Август»
# для счёта от 20.08) — коммуналка/эксплуатация не меняются, тот же месяц
_PDF_LAYOUT_VERSION = 7


def _canonical_invoice_key(guid: str) -> str:
    g = (guid or "").strip().lower()
    if g.startswith("@uuid:"):
        g = g[6:].strip()
    return g


def _invoice_keys_relaxed_match(a: str, b: str) -> bool:
    """Совпадение GUID счёта; допускает опечатку в одном символе 4-й группы (COM: b51d/b51c)."""
    ka = _canonical_invoice_key(a)
    kb = _canonical_invoice_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    pa, pb = ka.split("-"), kb.split("-")
    if len(pa) != 5 or len(pb) != 5:
        return False
    if pa[0] != pb[0] or pa[1] != pb[1] or pa[2] != pb[2] or pa[4] != pb[4]:
        return False
    if pa[3] == pb[3]:
        return True
    if len(pa[3]) != len(pb[3]):
        return False
    return sum(x != y for x, y in zip(pa[3], pb[3])) <= 1


def _resolve_invoice_line_key(inv_id: str, lines_by_id: dict) -> Optional[str]:
    """UID из платежа/запроса → ключ в batch-индексе строк счёта."""
    raw = (inv_id or "").strip()
    if not raw or not lines_by_id:
        return None
    if raw in lines_by_id:
        return raw
    target = _canonical_invoice_key(raw)
    for link in lines_by_id:
        if _canonical_invoice_key(link) == target:
            return link
        if _invoice_keys_relaxed_match(link, raw):
            return link
    return None


def _line_items_total_amount(lines: list[dict]) -> float:
    return sum(
        _first_float(row, "amount", "Сумма", "Amount") for row in (lines or [])
    )


def _payments_for_invoice(
    payments_map: dict[str, list],
    invoice_id: str,
) -> list[dict]:
    key = _canonical_invoice_key(invoice_id)
    if not key:
        return []
    if key in payments_map:
        return list(payments_map[key])
    for pay_key, items in payments_map.items():
        if _invoice_keys_relaxed_match(pay_key, key):
            return list(items)
    return []


def _parse_date_value(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _pdf_cache_meta_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".pdf.meta.json")


def _pdf_payload_has_supplier_banks(payload: Optional[dict]) -> bool:
    if not payload:
        return False
    return bool(
        str(payload.get("supplier_iik") or "").strip()
        and str(payload.get("supplier_bik") or "").strip()
    )


def _write_pdf_cache_meta(pdf_path: Path, payload: dict) -> None:
    try:
        meta = {
            "layout_version": _PDF_LAYOUT_VERSION,
            "supplier_iik": str(payload.get("supplier_iik") or "").strip(),
            "supplier_bik": str(payload.get("supplier_bik") or "").strip(),
            "supplier_bank_name": str(payload.get("supplier_bank_name") or "").strip(),
            "payment_knp": str(payload.get("payment_knp") or "").strip(),
        }
        _pdf_cache_meta_path(pdf_path).write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("PDF cache meta write failed for %s: %s", pdf_path, exc)


def _cached_pdf_layout_ok(pdf_path: Path) -> bool:
    meta_path = _pdf_cache_meta_path(pdf_path)
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    try:
        return int(meta.get("layout_version") or 0) >= _PDF_LAYOUT_VERSION
    except (TypeError, ValueError):
        return False


def _cached_pdf_has_supplier_banks(pdf_path: Path) -> bool:
    meta_path = _pdf_cache_meta_path(pdf_path)
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return bool(
        str(meta.get("supplier_iik") or "").strip()
        and str(meta.get("supplier_bik") or "").strip()
    )


def _try_reuse_cached_pdf(
    path: Path,
    invoice_id: str,
    *,
    require_supplier_banks: bool = False,
) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age > _PDF_CACHE_MAX_AGE:
            return None
        data = path.read_bytes()
        if len(data) < 500 or not data.startswith(b"%PDF"):
            return None
        if not _cached_pdf_layout_ok(path):
            logger.info(
                "Nova: skip cached PDF for %s — устаревшая вёрстка (layout < %s)",
                invoice_id,
                _PDF_LAYOUT_VERSION,
            )
            return None
        if require_supplier_banks and not _cached_pdf_has_supplier_banks(path):
            logger.info(
                "Nova: skip cached PDF for %s — нет ИИК/БИК в meta (пересборка)",
                invoice_id,
            )
            return None
        logger.info(
            "Nova: reuse cached PDF for %s (%s bytes, age %s)",
            invoice_id,
            len(data),
            age,
        )
        return str(path.resolve())
    except OSError:
        return None


def _calculate_due_date(invoice_date: date, due_day: int = 5) -> date:
    """due_day-е число МЕСЯЦА, СЛЕДУЮЩЕГО за месяцем счёта.

    Раньше возвращала due_day-е число ТОГО ЖЕ месяца (invoice_date.replace),
    из-за чего для счёта, выставленного после due_day (типично — аренда за
    август выставляется 20.08, due_day=5), получался срок оплаты РАНЬШЕ
    даты самого счёта. См. _invoice_due_dates() выше и
    invoice_service_type.due_date_in_invoice_month — тот же класс бага,
    исправленный тем же способом (реальный кейс: счёт от 20.08.2026 с
    "Крайний срок оплаты: 05.08.2026" вместо 05.09.2026)."""
    if invoice_date.month == 12:
        year, month = invoice_date.year + 1, 1
    else:
        year, month = invoice_date.year, invoice_date.month + 1
    last_day = monthrange(year, month)[1]
    day = min(max(due_day, 1), last_day)
    return date(year, month, day)


def _normalize_counterparty_row(row: dict) -> dict:
    """Единый phoneNumber для Counterparty.from_dict (COM/OData alias)."""
    if not isinstance(row, dict):
        return {}
    normalized = dict(row)
    if (normalized.get("phoneNumber") or normalized.get("phone") or "").strip():
        return normalized
    for key, val in row.items():
        key_lower = str(key).lower()
        if key_lower in ("phonenumber", "phone", "телефон", "номертелефона", "mobile"):
            phone = str(val or "").strip()
            if phone:
                normalized["phoneNumber"] = phone
                normalized["phone"] = phone
                break
    return normalized


_ZERO_GUID = "00000000-0000-0000-0000-000000000000"

_COUNTERPARTY_PARENT_SCRIPT_NAME = "BUH: Контрагенты (parent/folder)"
# Важно: top-level op должен быть известен Nova (как у groups/counterparties),
# иначе COM-агент отвечает «Ошибка при обращении к 1С».
_COUNTERPARTY_PARENT_SCRIPT_BODY = {
    "op": "counterparty_groups",
    "_doc": (
        "Карта id→parent для фильтра папок на портале. "
        "Имя папки (fullName) подставляется из BUH: Группы контрагентов. "
        "Не заменяет BUH: Контрагенты."
    ),
    "vars": {},
    "steps": [
        {
            "id": "counterparty_parents",
            "op": "query",
            "text": (
                "ВЫБРАТЬ УНИКАЛЬНЫЙИДЕНТИФИКАТОР(Контрагенты.Ссылка) КАК id, "
                "УНИКАЛЬНЫЙИДЕНТИФИКАТОР(Контрагенты.Родитель) КАК parent "
                "ИЗ Справочник.Контрагенты КАК Контрагенты "
                "ГДЕ НЕ Контрагенты.ЭтоГруппа"
            ),
        }
    ],
    "return": ["counterparty_parents"],
}


def _is_empty_guid(value: Optional[str]) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return True
    return raw.replace("-", "") == "0" * 32 or raw == _ZERO_GUID


def _parent_rows_from_results(results: dict) -> list[dict]:
    block = results.get("counterparty_parents")
    if isinstance(block, dict):
        rows = query_step_to_dicts(block)
        if rows:
            return [r for r in rows if isinstance(r, dict)]
    batch = results.get("batch")
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if isinstance(parts, list):
        for part in reversed(parts):
            if not isinstance(part, dict):
                continue
            rows = query_step_to_dicts(part)
            if rows and isinstance(rows[0], dict) and (
                "parent" in rows[0] or "folderName" in rows[0]
            ):
                return [r for r in rows if isinstance(r, dict)]
    return []


def _group_rows_from_results(results: dict) -> list[dict]:
    block = results.get("counterparty_groups")
    if isinstance(block, dict):
        rows = query_step_to_dicts(block)
        if rows:
            return [r for r in rows if isinstance(r, dict)]
    return []


def _looks_like_counterparty_row(row: dict) -> bool:
    return bool((row.get("id") or row.get("fullName") or row.get("full_name") or "").strip())


def _counterparty_rows_from_results(results: dict) -> list[dict]:
    """Строки контрагентов: op=query (columns+items) или готовые dict items."""
    block = results.get("counterparties")
    if isinstance(block, dict):
        rows = query_step_to_dicts(block)
        if rows:
            return [_normalize_counterparty_row(r) for r in rows if isinstance(r, dict)]

    batch = results.get("batch")
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if isinstance(parts, list):
        for part in reversed(parts):
            if not isinstance(part, dict):
                continue
            rows = query_step_to_dicts(part)
            if rows and _looks_like_counterparty_row(rows[0]):
                return [_normalize_counterparty_row(r) for r in rows if isinstance(r, dict)]

    raw_items = _extract_batch_items(results)
    if raw_items and isinstance(raw_items[0], dict):
        return [_normalize_counterparty_row(r) for r in raw_items if isinstance(r, dict)]
    return []


def _iter_nova_query_steps(results: dict):
    """Все шаги op=query в ответе Nova (counterparties batch может содержать контакты)."""
    if not isinstance(results, dict):
        return
    for block in results.values():
        if isinstance(block, dict) and ("columns" in block or "items" in block):
            yield block
    batch = results.get("batch")
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and ("columns" in part or "items" in part):
                yield part


def _phones_by_counterparty_from_results(results: dict) -> dict[str, str]:
    """
    Телефоны из batch Nova/COM: колонка phoneNumber и регистр контактной информации.
    В 1С телефон часто лежит в КонтактнаяИнформация, а не в справочнике Контрагенты.
    """
    from app.services.odata_1c_client import (
        _contact_owner_key,
        _extract_guid_key,
        _extract_phone_from_row,
    )

    phones: dict[str, str] = {}
    for step in _iter_nova_query_steps(results):
        for row in query_step_to_dicts(step):
            if not isinstance(row, dict):
                continue
            cp_id = _extract_guid_key(
                _first_str(row, "id", "Ref_Key", "ref", "Контрагент", "Контрагент_Key")
            )
            phone = _extract_phone_from_row(row)
            if cp_id and phone and cp_id not in phones:
                phones[cp_id] = phone
                continue
            owner = _contact_owner_key(row)
            if not owner:
                continue
            type_hint = _first_str(
                row, "Тип", "Type", "Вид", "ВидПредставление", "kind"
            ).lower()
            if type_hint and "телефон" not in type_hint and "phone" not in type_hint:
                if "адрес" in type_hint or "address" in type_hint or "email" in type_hint:
                    continue
            phone = _extract_phone_from_row(row)
            if phone and owner not in phones:
                phones[owner] = phone
    return phones


def _enrich_counterparties_phones(
    counterparties: list[Counterparty],
    phones_by_cp: dict[str, str],
) -> list[Counterparty]:
    if not phones_by_cp:
        return counterparties
    for cp in counterparties:
        if (cp.phone or cp.phone_number or "").strip():
            continue
        cp_key = (cp.id or "").strip().lower()
        phone = phones_by_cp.get(cp_key)
        if phone:
            cp.phone = phone
            cp.phone_number = phone
    return counterparties


def _extract_batch_items(results: dict) -> list[dict]:
    batch = results.get("batch")
    if isinstance(batch, dict) and isinstance(batch.get("batch"), list):
        batch = batch["batch"]
    if isinstance(batch, list):
        for entry in reversed(batch):
            if isinstance(entry, dict) and isinstance(entry.get("items"), list):
                return entry["items"]
    for key in ("invoices", "counterparties", "payments"):
        block = results.get(key)
        if isinstance(block, dict) and isinstance(block.get("items"), list):
            return block["items"]
    return []


def _looks_like_balance_row(row: dict) -> bool:
    """
    Строка by_counterparty: debit/credit + идентификатор ИЛИ хотя бы имя контрагента.
    COM-скрипты (buh COM, в отличие от OData) иногда отдают by_counterparty без
    Ref/id вообще — только counterparty_name. Такие строки тоже нужно принимать,
    id для них резолвится позже по имени (см. counterparty_balance_service).
    """
    if not isinstance(row, dict):
        return False
    has_identity = bool(
        row.get("counterparty_id")
        or row.get("Контрагент")
        or row.get("id")
        or row.get("Ref")
        or row.get("Ссылка")
        or row.get("counterparty_name")
        or row.get("КонтрагентПредставление")
        or row.get("Наименование")
        or row.get("name")
        or row.get("fullName")
    )
    has_amounts = (
        "debit" in row
        or "debit_sum" in row
        or "Дебет" in row
        or "credit" in row
        or "credit_sum" in row
        or "Кредит" in row
    )
    return has_identity and has_amounts


def _normalize_balance_row(row: dict) -> Optional[dict]:
    cp_id = _first_str(
        row,
        "counterparty_id",
        "Контрагент",
        "id",
        "Ref",
        "Ссылка",
    )
    name = _first_str(
        row,
        "counterparty_name",
        "КонтрагентПредставление",
        "Наименование",
        "name",
        "fullName",
    )
    if not cp_id and not name:
        return None
    debit = _first_float(row, "debit", "debit_sum", "Дебет", "debitSum")
    credit = _first_float(row, "credit", "credit_sum", "Кредит", "creditSum")
    return {
        # Пусто, если COM не отдал id — резолвится по имени в counterparty_balance_service.
        "counterparty_id": (_canonical_invoice_key(cp_id) or cp_id.strip().lower()) if cp_id else "",
        "counterparty_name": name,
        "debit": debit,
        "credit": credit,
    }


def _balance_rows_from_results(results: dict) -> list[dict]:
    """
    BUH balance → by_counterparty.
    Форматы: именованная секция, query columns+items, batch-части.
    """
    if not isinstance(results, dict):
        return []

    out: list[dict] = []

    for key, block in results.items():
        key_l = str(key).lower()
        if key_l in ("by_counterparty", "bycounterparty") or (
            "counterparty" in key_l and "agreement" not in key_l and "group" not in key_l
        ):
            rows: list[dict] = []
            if isinstance(block, list):
                rows = [r for r in block if isinstance(r, dict)]
            elif isinstance(block, dict):
                rows = query_step_to_dicts(block)
            for row in rows:
                if not _looks_like_balance_row(row):
                    continue
                norm = _normalize_balance_row(row)
                if norm:
                    out.append(norm)
            if out:
                return out

    batch = results.get("batch")
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            rows = query_step_to_dicts(part)
            if not rows or not _looks_like_balance_row(rows[0]):
                continue
            for row in rows:
                norm = _normalize_balance_row(row)
                if norm:
                    out.append(norm)
            if out:
                return out

    return out


def _looks_like_aging_row(row: dict) -> bool:
    """Строка секции aging (balance → по срокам): нужна привязка к контрагенту
    + хотя бы один из бакетов current/days30/days60/days90/over120/unknown/total."""
    if not isinstance(row, dict):
        return False
    has_identity = bool(
        row.get("counterparty_id")
        or row.get("Контрагент")
        or row.get("id")
        or row.get("Ref")
        or row.get("Ссылка")
        or row.get("counterparty_name")
        or row.get("КонтрагентПредставление")
        or row.get("Наименование")
        or row.get("name")
    )
    has_bucket = any(
        key in row
        for key in ("current", "days30", "days60", "days90", "over120", "unknown", "total")
    )
    return has_identity and has_bucket


def _normalize_aging_row(row: dict) -> Optional[dict]:
    cp_id = _first_str(row, "counterparty_id", "Контрагент", "id", "Ref", "Ссылка")
    name = _first_str(row, "counterparty_name", "КонтрагентПредставление", "Наименование", "name", "fullName")
    if not cp_id and not name:
        return None
    return {
        "counterparty_id": (_canonical_invoice_key(cp_id) or cp_id.strip().lower()) if cp_id else "",
        "counterparty_name": name,
        "aging_current": _first_float(row, "current"),
        "aging_30": _first_float(row, "days30"),
        "aging_60": _first_float(row, "days60"),
        "aging_90": _first_float(row, "days90"),
        "aging_over120": _first_float(row, "over120"),
        "aging_unknown": _first_float(row, "unknown"),
        "aging_total": _first_float(row, "total"),
    }


def _aging_rows_from_results(results: dict) -> list[dict]:
    """BUH balance → aging (долг по срокам). Тот же ответ, что и by_counterparty —
    отдельная секция, не отдельный вызов."""
    if not isinstance(results, dict):
        return []
    out: list[dict] = []
    for key, block in results.items():
        if str(key).lower() != "aging":
            continue
        rows: list[dict] = []
        if isinstance(block, list):
            rows = [r for r in block if isinstance(r, dict)]
        elif isinstance(block, dict):
            rows = query_step_to_dicts(block)
        for row in rows:
            if not _looks_like_aging_row(row):
                continue
            norm = _normalize_aging_row(row)
            if norm:
                out.append(norm)
        return out
    return out


def _batch_part_items(part) -> list[dict]:
    if not isinstance(part, dict):
        return []
    items = part.get("items")
    if not isinstance(items, list) or not items:
        return []
    return [row for row in items if isinstance(row, dict)]


def _batch_part_looks_like_invoice_headers(items: list[dict], columns: list[str]) -> bool:
    """Шапка счёта: по columns или по ключам строки (Nova иногда отдаёт columns=null)."""
    if "СчетНаОплату" in columns or "КонтрагентПредставление" in columns:
        return True
    if not items:
        return False
    keys = set(items[0].keys())
    has_invoice_ref = "СчетНаОплату" in keys or "КонтрагентПредставление" in keys
    has_header_fields = "Номер" in keys or "СуммаДокумента" in keys or "СтатусОплаты" in keys
    return has_invoice_ref and has_header_fields


def _batch_part_looks_like_invoice_lines(items: list[dict], columns: list[str]) -> bool:
    if "НоменклатураПредставление" in columns and "Ссылка" in columns:
        return True
    if not items:
        return False
    keys = set(items[0].keys())
    return (
        "НоменклатураПредставление" in keys
        and "Ссылка" in keys
        and "СуммаДокумента" not in keys
        and "Номер" not in keys
    )


def _extract_invoice_header_items(results: dict) -> list[dict]:
    """Return invoice header rows from batch payload when present."""
    batch = results.get("batch")
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if isinstance(parts, list):
        for part in parts:
            items = _batch_part_items(part)
            if not items:
                continue
            columns = [str(col) for col in ((part or {}).get("columns") or [])]
            if _batch_part_looks_like_invoice_headers(items, columns):
                return items
    return []


def _extract_invoice_line_items_batch(results: dict) -> list[dict]:
    """Return invoice line rows from batch payload when present."""
    batch = results.get("batch")
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if isinstance(parts, list):
        for part in parts:
            items = _batch_part_items(part)
            if not items:
                continue
            columns = [str(col) for col in ((part or {}).get("columns") or [])]
            if _batch_part_looks_like_invoice_lines(items, columns):
                return items
    return []


def _first_str(row: dict, *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _first_float(row: dict, *keys: str) -> float:
    for key in keys:
        val = row.get(key)
        if val is None or val == "":
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return 0.0


def _line_item_name(row: dict) -> str:
    """ Не брать сырой Ref/GUID из поля Номенклатура."""
    from app.services.odata_1c_client import _looks_like_guid

    for key in (
        "name",
        "Содержание",
        "НоменклатураПредставление",
        "Номенклатура_Description",
        "Description",
        "Наименование",
        "Номенклатура",  # иногда строка-представление; GUID отфильтруем ниже
    ):
        val = row.get(key)
        if isinstance(val, dict):
            val = (
                val.get("Description")
                or val.get("Наименование")
                or val.get("Представление")
                or val.get("name")
            )
        text = str(val).strip() if val is not None else ""
        if not text:
            continue
        if _looks_like_guid(text):
            continue
        return text
    return ""


def _normalize_line_items(raw) -> list[dict]:
    if not raw:
        return []
    rows = raw
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        rows = raw["items"]
    if not isinstance(rows, list):
        return []
    items: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _line_item_name(row)
        if name:
            items.append({"name": name})
    return items


def _inline_line_items_from_row(row: dict) -> list[dict]:
    items: list[dict] = []
    for key in ("Услуги", "Товары", "services", "goods", "items", "lines"):
        block = row.get(key)
        items.extend(_normalize_line_items(block))
    return items


def _extract_line_items_from_results(results: dict) -> list[dict]:
    for key in ("services", "goods", "items", "lines", "Услуги", "Товары"):
        block = results.get(key)
        items = _normalize_line_items(block)
        if items:
            return items
    invoice = results.get("invoice")
    if isinstance(invoice, dict):
        for key in ("services", "goods", "items", "lines", "Услуги", "Товары"):
            items = _normalize_line_items(invoice.get(key))
            if items:
                return items
    batch_items = _extract_batch_items(results)
    for row in batch_items:
        if isinstance(row, dict):
            items = _inline_line_items_from_row(row)
            if items:
                return items
    return []


def _normalize_status_oplaty(raw: str) -> Optional[str]:
    """Нормализация поля СтатусОплаты из Nova/Postman - paid|unpaid|overdue."""
    low = (raw or "").strip().lower()
    if not low:
        return None
    if low in ("paid", "оплачен", "оплачено", "true", "истина"):
        return "paid"
    if low in ("overdue", "просрочен", "просрочено"):
        return "overdue"
    if low in (
        "unpaid",
        "не оплачен",
        "не оплачено",
        "неоплачен",
        "неоплачено",
        "false",
        "ложь",
    ):
        return "unpaid"
    # Любое другое непустое значение из СтатусОплаты — как unpaid (не пересчитывать).
    return "unpaid"


def _payment_status_from_amounts(row: dict, amount: float, paid: float) -> str:
    # Приоритет: СтатусОплаты из скрипта 1С (как в Postman).
    status_oplaty = _first_str(row, "СтатусОплаты").strip()
    if status_oplaty:
        return _normalize_status_oplaty(status_oplaty) or "unpaid"

    if row.get("Оплачен") is True or row.get("Paid") is True:
        return "paid"
    # "Статус" намеренно не в этом списке — по BUH-API-reference это ненадёжное
    # поле 1С ("часто пустой или неверный"), в отличие от СтатусОплаты выше
    # (которое 1С считает сама для этой цели). Если сюда дошли — доверенного
    # статуса от 1С нет вообще, честнее сразу считать по суммам, чем случайно
    # поймать мусор из "Статус" и получить неверный "unpaid" catch-all.
    payment_status_raw = _first_str(
        row,
        "PaymentStatus",
        "СостояниеОплаты",
        "Оплата",
        "Оплачен",
        "Paid",
    ).strip()
    normalized = _normalize_status_oplaty(payment_status_raw)
    if normalized:
        return normalized
    # Нет явного статуса от 1С — считаем по суммам (paid/partial/unpaid, без
    # учёта due_date — это не тот код-путь, где известен срок оплаты).
    return payment_coverage_status(amount, paid)


def _nova_header_to_invoice(invoice_id: str, header: dict, lines: list[dict]) -> Invoice:
    row = dict(header)
    row.setdefault("Ref_Key", invoice_id)
    amount = _first_float(row, "СуммаДокумента", "Amount", "Сумма", "amount")
    normalized_lines = _normalize_line_items(lines) if lines else []
    if not amount and normalized_lines:
        amount = sum(float(item.get("amount") or 0) for item in normalized_lines)
    paid = _first_float(
        row,
        "СуммаОплат",
        "СуммаОплачена",
        "Оплачено",
        "PaidAmount",
        "paid_amount",
        "СуммаОплаты",
    )
    payment_status = _payment_status_from_amounts(row, amount, paid)
    raw_date = _first_str(row, "Date", "Дата", "date")
    if "T" in raw_date:
        raw_date = raw_date.split("T")[0]
    elif " " in raw_date:
        raw_date = raw_date.split(" ")[0]
    return Invoice.from_dict(
        {
            "id": _canonical_invoice_key(invoice_id) or invoice_id,
            "number": _first_str(row, "Number", "Номер", "number"),
            "date": str(raw_date)[:10],
            "counterparty_id": _first_str(
                row,
                "Контрагент_Key",
                "Counterparty_Key",
                "Покупатель_Key",
                "Контрагент",
                "counterparty_id",
            ),
            "counterparty_name": _first_str(
                row,
                "КонтрагентПредставление",
                "Counterparty_Description",
                "Description",
                "counterparty_name",
            ),
            "amount": amount,
            "currency": _first_str(row, "Валюта", "Currency", "currency") or "KZT",
            # Не "Статус" — по BUH-API-reference это ненадёжное поле 1С, и для
            # onec.buh.invoices (в отличие от avr) нет надёжного аналога "Проведен"
            # вообще. Честнее оставить пусто, чем показать вводящий в заблуждение
            # posted/draft-лейбл (см. _serialize_invoice_row в app/api/payments.py).
            "status": "",
            "paid_amount": paid,
            "payment_status": payment_status,
            "bin": _first_str(row, "БИН", "bin", "ИНН", "iin"),
            "items": normalized_lines,
        }
    )


def _nova_row_to_invoice(row: dict) -> Invoice:
    ref = _first_str(
        row,
        "Ref_Key",
        "Ref",
        "Key",
        "id",
        "СчетНаОплатуПокупателю_Key",
        "СчетНаОплату_Key",
        "СчетНаОплату",
    )
    cp_key = _first_str(
        row,
        "Контрагент_Key",
        "Counterparty_Key",
        "Покупатель_Key",
        "Контрагент",
        "counterparty_id",
    )
    amount = _first_float(row, "СуммаДокумента", "Amount", "Сумма", "amount")
    paid = _first_float(
        row,
        "СуммаОплат",
        "СуммаОплачена",
        "Оплачено",
        "PaidAmount",
        "paid_amount",
    )
    payment_status = _payment_status_from_amounts(row, amount, paid)
    raw_date = _first_str(row, "Date", "Дата", "date")
    inline_items = _inline_line_items_from_row(row)
    return Invoice.from_dict(
        {
            "id": ref,
            "number": _first_str(row, "Number", "Номер", "number"),
            "date": str(raw_date)[:10],
            "counterparty_id": cp_key,
            "counterparty_name": _first_str(
                row,
                "КонтрагентПредставление",
                "Counterparty_Description",
                "Description",
                "counterparty_name",
            ),
            "amount": amount,
            "currency": _first_str(row, "Валюта", "Currency", "currency") or "KZT",
            # Не "Статус" — по BUH-API-reference это ненадёжное поле 1С, и для
            # onec.buh.invoices (в отличие от avr) нет надёжного аналога "Проведен"
            # вообще. Честнее оставить пусто, чем показать вводящий в заблуждение
            # posted/draft-лейбл (см. _serialize_invoice_row в app/api/payments.py).
            "status": "",
            "paid_amount": paid,
            "payment_status": payment_status,
            "bin": _first_str(row, "БИН", "bin", "ИНН", "iin"),
            "items": inline_items,
        }
    )


def _guid_prefix7(guid: str) -> str:
    return (guid or "").strip().lower().split("-")[0][:7]


def _guid_suffix(guid: str) -> str:
    parts = (guid or "").strip().lower().split("-")
    return "-".join(parts[1:]) if len(parts) == 5 else ""


def _orphan_invoice_counterparty_map(counterparties: list) -> dict[str, str]:
    """Сопоставление неоплаченных счетов (только строки, без оплат) с контрагентом."""
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for cp in counterparties:
        cp_id = (getattr(cp, "id", None) or "").strip().lower()
        if not cp_id:
            continue
        by_key[(_guid_prefix7(cp_id), _guid_suffix(cp_id))].append(cp_id)

    mapping: dict[str, str] = {}
    for key, cp_ids in by_key.items():
        if len(cp_ids) != 1:
            continue
        mapping[key] = cp_ids[0]
    return mapping


def _is_line_item_batch(rows: list[dict]) -> bool:
    if not rows:
        return False
    sample = rows[0]
    return bool(
        _first_str(sample, "НоменклатураПредставление", "Содержание")
        and _first_str(sample, "Ссылка", "Ref_Key", "Ref", "id")
        and not _first_str(sample, "Ref_Key", "Контрагент_Key", "Контрагент")
    )


def _nova_uid_var(invoice_id: str) -> str:
    raw = (invoice_id or "").strip()
    if not raw:
        return raw
    if raw.startswith("@uuid:"):
        return raw
    return f"@uuid:{raw}"


def _invoice_by_id_sections(results: dict) -> tuple[Optional[dict], list[dict]]:
    batch = results.get("batch") or {}
    parts = batch.get("batch") if isinstance(batch, dict) else batch
    if not isinstance(parts, list):
        return None, []

    header: Optional[dict] = None
    lines: list[dict] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        items = part.get("items")
        if not isinstance(items, list) or not items:
            continue
        columns = [str(col) for col in (part.get("columns") or [])]
        if "СчетНаОплату" in columns or "КонтрагентПредставление" in columns:
            header = items[0]
        elif "НоменклатураПредставление" in columns:
            lines = items
    return header, lines


def _org_from_results(results: dict) -> dict:
    org = results.get("org")
    if not isinstance(org, dict):
        return {}
    row = query_step_first_row(org)
    if row:
        return row
    if any(
        str(org.get(key) or "").strip()
        for key in (
            "supplier_name",
            "supplier_bin",
            "supplier_iik",
            "supplier_bik",
            "supplier_kbe",
            "payment_knp",
        )
    ):
        return org
    return {}


def _merge_supplier_requisites(payload: dict, tenant=None) -> dict:
    if not payload or tenant is None:
        return payload
    pairs = (
        ("supplier_name", "legal_name"),
        ("supplier_bin", "bin_value"),
        ("supplier_iik", "invoice_iik"),
        ("supplier_kbe", "invoice_kbe"),
        ("supplier_bank_name", "invoice_bank_name"),
        ("supplier_bik", "invoice_bank_bik"),
        ("supplier_address", "invoice_supplier_address"),
        ("contract_text", "invoice_contract_text"),
    )
    for payload_key, tenant_attr in pairs:
        current = str(payload.get(payload_key) or "").strip()
        if current:
            continue
        val = getattr(tenant, tenant_attr, None)
        if val is not None and str(val).strip():
            payload[payload_key] = str(val).strip()

    if not str(payload.get("payment_knp") or "").strip():
        # 1С не дал КНП для этого документа (реальный, не редкий случай —
        # см. Astranium/Maxi Mall, запрошено 2026-09-02). Сначала пробуем
        # угадать по типу услуги строк счёта (855 аренда / 855 эксплуатация
        # и маркетинг / 856 коммуналка — DEFAULT_KNP_BY_SERVICE_TYPE): точнее
        # одного общего дефолта на весь тенант. Только если тип не входит в
        # эту карту (вывеска/АССП/долг/прочее/не распознано) — падаем на
        # старый общий tenant.invoice_payment_knp, как раньше.
        knp = ""
        for service_type in resolve_invoice_service_types(payload.get("items") or []):
            knp = DEFAULT_KNP_BY_SERVICE_TYPE.get(service_type, "")
            if knp:
                break
        if not knp:
            tenant_knp = getattr(tenant, "invoice_payment_knp", None)
            knp = str(tenant_knp).strip() if tenant_knp is not None else ""
        if knp:
            payload["payment_knp"] = knp

    if not str(payload.get("supplier_name") or "").strip():
        name = (getattr(tenant, "legal_name", None) or getattr(tenant, "name", None) or "").strip()
        if name:
            payload["supplier_name"] = name
    return payload


def _build_pdf_payload_from_nova_invoice(
    invoice_id: str,
    header: Optional[dict],
    lines: list[dict],
    *,
    org: Optional[dict] = None,
    tenant=None,
    enrichment: Optional[dict] = None,
    counterparty: Optional[dict] = None,
) -> Optional[dict]:
    if not header:
        return None
    raw_date = _first_str(header, "Дата", "Date", "date")
    if "T" in raw_date:
        raw_date = raw_date.split("T")[0]
    elif " " in raw_date:
        raw_date = raw_date.split(" ")[0]

    enrich = enrichment or {}
    line_units: dict[str, str] = enrich.get("line_units") or {}
    cp_info = counterparty or {}

    items: list[dict] = []
    vat_from_lines = 0.0
    for row in lines:
        name = _line_item_name(row)
        if not name:
            continue
        row_vat = _first_float(row, "СуммаНДС", "VAT", "НДС")
        if row_vat:
            vat_from_lines += float(row_vat)
        unit = (
            _first_str(row, "ЕдиницаИзмерения", "Единица", "unit")
            or line_units.get(name)
            or "услуга"
        )
        items.append(
            {
                "name": name,
                "quantity": _first_float(row, "Количество", "Quantity") or 1,
                "price": _first_float(row, "Цена", "Price"),
                "amount": _first_float(row, "Сумма", "Amount", "amount"),
                "unit": unit,
            }
        )

    amount = _first_float(header, "СуммаДокумента", "Amount", "amount")
    if not amount and items:
        amount = sum(float(item.get("amount") or 0) for item in items)

    vat = _first_float(header, "СуммаНДС", "VAT", "НДС")
    if not vat and vat_from_lines:
        vat = float(vat_from_lines)

    cp_id = _first_str(header, "Контрагент", "Контрагент_Key", "counterparty_id")
    cp_name = (
        _first_str(header, "КонтрагентПредставление", "counterparty_name")
        or str(enrich.get("counterparty_name_full") or "").strip()
        or str(cp_info.get("name") or "").strip()
    )
    cp_bin = (
        _first_str(header, "БИН", "bin")
        or str(enrich.get("counterparty_bin") or "").strip()
        or str(cp_info.get("bin") or "").strip()
    )
    cp_kbe = str(enrich.get("counterparty_kbe") or cp_info.get("kbe") or "").strip()
    cp_phone = str(cp_info.get("phone") or "").strip()
    cp_address = str(cp_info.get("address") or "").strip()

    payload = {
        "id": invoice_id,
        "number": _first_str(header, "Номер", "Number", "number"),
        "date": raw_date,
        "counterparty_id": cp_id,
        "counterparty_name": cp_name,
        "counterparty_bin": cp_bin,
        "counterparty_kbe": cp_kbe,
        "counterparty_address": cp_address,
        "counterparty_phone": cp_phone,
        "amount": amount,
        "vat": vat,
        "currency": _first_str(header, "Валюта", "Currency") or "KZT",
        "items": items,
        "contract_text": str(enrich.get("contract_text") or "").strip() or "Без договора",
        "payment_knp": str(enrich.get("payment_knp") or "").strip(),
    }

    if org:
        for key in (
            "supplier_name",
            "supplier_bin",
            "supplier_iik",
            "supplier_bank_name",
            "supplier_bik",
            "supplier_kbe",
            "supplier_address",
            "payment_knp",
            "contract_text",
        ):
            val = _first_str(org, key)
            if val and not str(payload.get(key) or "").strip():
                payload[key] = val

    for key in (
        "supplier_name",
        "supplier_bin",
        "supplier_iik",
        "supplier_bank_name",
        "supplier_bik",
        "supplier_kbe",
        "supplier_address",
        "payment_knp",
        "contract_text",
    ):
        val = str(enrich.get(key) or "").strip()
        if val and not str(payload.get(key) or "").strip():
            payload[key] = val

    supplier = {
        "name": str(payload.get("supplier_name") or "").strip(),
        "bin": str(payload.get("supplier_bin") or "").strip(),
        "kbe": str(payload.get("supplier_kbe") or "").strip(),
        "iik": str(payload.get("supplier_iik") or "").strip(),
        "bank_name": str(payload.get("supplier_bank_name") or "").strip(),
        "bank_bik": str(payload.get("supplier_bik") or "").strip(),
        "address": str(payload.get("supplier_address") or "").strip(),
        "phones": [],
    }
    if supplier.get("name") or supplier.get("bin") or supplier.get("iik"):
        payload["supplier"] = supplier
        for src_key, dst_key in (
            ("name", "supplier_name"),
            ("bin", "supplier_bin"),
            ("kbe", "supplier_kbe"),
            ("iik", "supplier_iik"),
            ("bank_name", "supplier_bank_name"),
            ("bank_bik", "supplier_bik"),
            ("address", "supplier_address"),
        ):
            if supplier.get(src_key) and not str(payload.get(dst_key) or "").strip():
                payload[dst_key] = supplier[src_key]

    return _merge_supplier_requisites(payload, tenant)


def _resolve_downloads_path(invoice_id: str) -> Path:
    cwd = Path.cwd()
    candidates = [
        cwd / "downloads",
        cwd / "backend" / "downloads",
        Path(__file__).resolve().parent.parent.parent / "downloads",
        Path(__file__).resolve().parent.parent / "downloads",
    ]
    safe_id = safe_filename_component(invoice_id)
    for downloads in candidates:
        try:
            downloads.mkdir(parents=True, exist_ok=True)
            return downloads / f"invoice_{safe_id}.pdf"
        except OSError:
            continue
    fallback = cwd / "downloads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / f"invoice_{safe_id}.pdf"


def _looks_like_pdf(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == b"%PDF"


def _decode_pdf_payload(raw: str) -> Optional[bytes]:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        data = base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError):
        return None
    return data if _looks_like_pdf(data) else None


def _extract_pdf_from_value(val) -> Optional[bytes]:
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        data = bytes(val)
        return data if _looks_like_pdf(data) else None
    if isinstance(val, str):
        if val.startswith("%PDF"):
            return val.encode("latin-1", errors="ignore")
        return _decode_pdf_payload(val)
    return None


def _extract_pdf_bytes_from_results(results: dict) -> Optional[bytes]:
    if not isinstance(results, dict):
        return None

    # Named step from print_form op (deploy_nova_invoice_pdf.py → id: "pdf")
    pdf_step = results.get("pdf")
    if isinstance(pdf_step, dict):
        for key in ("pdf_base64", "pdf", "content", "data", "file_base64", "body"):
            data = _extract_pdf_from_value(pdf_step.get(key))
            if data:
                return data

    blob = results.get("blob")
    if isinstance(blob, dict):
        data = _extract_pdf_from_value(blob.get("base64") or blob.get("pdf_base64"))
        if data:
            return data

    direct_keys = (
        "pdf",
        "pdf_base64",
        "file",
        "file_base64",
        "content",
        "data",
        "document",
        "base64",
        "body",
        "Файл",
        "Печать",
        "ПечатнаяФорма",
    )
    for key in direct_keys:
        if key in results:
            data = _extract_pdf_from_value(results.get(key))
            if data:
                return data

    invoice = results.get("invoice")
    if isinstance(invoice, dict):
        for key in direct_keys:
            if key in invoice:
                data = _extract_pdf_from_value(invoice.get(key))
                if data:
                    return data

    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in ("pdf", "файл", "печат")):
                    data = _extract_pdf_from_value(value)
                    if data:
                        return data
                found = walk(value)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if found:
                    return found
        return None

    return walk(results)


class NovaBuh1CClient:
    """Nova script runner with the same surface as OData1CClient for read paths."""

    # Виды телефонов — как в OData City Mall / Postman mobile_vid
    CONTACT_KIND_PHONE = "c5bb357f-c3b0-48ba-8a12-a42cbf99a845"
    CONTACT_KIND_MOBILE = "f9e52726-2faf-4dca-85d0-559b80df2c53"
    PHONE_CONTACT_KINDS = (CONTACT_KIND_MOBILE, CONTACT_KIND_PHONE)

    def __init__(
        self,
        organization_id: int,
        service: Optional[Nova1CService] = None,
        script_ids: Optional[dict[str, int]] = None,
    ):
        self._organization_id = int(organization_id)
        self._service = service or get_nova_1c_service()
        self._access_token: Optional[str] = None
        self._sync_token: Optional[str] = None
        self.last_connect_error: Optional[str] = None
        self.last_warning: Optional[str] = None
        self._script_ids: dict[str, int] = {}
        self._script_ids_override = dict(script_ids or {})
        self._agent_id: Optional[str] = None
        self._odata_org: bool = False
        self._invoice_pdf_script_body: Optional[dict] = None
        self._counterparty_name_cache: dict[str, str] = {}
        self._invoice_lines_by_id: Optional[Dict[str, list[dict]]] = None
        self._invoice_headers_by_id: Optional[Dict[str, dict]] = None
        self._orphan_cp_by_invoice: Optional[dict[str, str]] = None
        self._agent_lookup_done: bool = False
        self._counterparties_cache: Optional[List[Counterparty]] = None

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token

    @property
    def sync_token(self) -> Optional[str]:
        return self._sync_token

    def authenticate(self, user: str = None, password: str = None) -> AuthResponse:
        self._ensure_scripts()
        self._access_token = "nova-script"
        self._sync_token = f"nova-org-{self._organization_id}"
        return AuthResponse(token=self._access_token, expires="")

    def close(self) -> None:
        self._access_token = None
        self._invoice_lines_by_id = None
        self._invoice_headers_by_id = None
        self._orphan_cp_by_invoice = None

    def _ensure_invoice_index(self, line_rows: Optional[list[dict]] = None) -> None:
        if self._invoice_lines_by_id is not None and self._invoice_headers_by_id is not None:
            return

        if line_rows is None:
            line_rows = _extract_batch_items(
                self._run("invoices").get("result", {}).get("results", {})
            )
        lines_by_id: dict[str, list[dict]] = defaultdict(list)
        for row in line_rows:
            link = _first_str(row, "Ссылка", "Ref_Key", "Ref", "id", "СчетНаОплату")
            name = _line_item_name(row)
            if link and name:
                lines_by_id[link].append(
                    {
                        "name": name,
                        "amount": _first_float(row, "Сумма", "amount"),
                    }
                )

        # Шапка: сумма = сумма строк ЭТОГО счёта (не СуммаДокумента из payments — там часто пара счетов).
        headers: dict[str, dict] = {}
        for inv_id, line_items in lines_by_id.items():
            headers[inv_id] = {
                "date": "",
                "counterparty_id": "",
                "counterparty_name": "",
                "number": "",
                "amount": _line_items_total_amount(line_items),
                "paid_amount": 0.0,
            }

        if self._script_ids.get("payments"):
            pay_rows = _extract_batch_items(
                self._run("payments").get("result", {}).get("results", {})
            )
            for row in pay_rows:
                raw_inv_id = _first_str(
                    row,
                    "СчетНаОплату",
                    "СчетНаОплатуПокупателю_Key",
                    "СчетНаОплату_Key",
                )
                if not raw_inv_id or raw_inv_id == _EMPTY_INVOICE_GUID:
                    continue
                inv_id = _resolve_invoice_line_key(raw_inv_id, lines_by_id)
                if not inv_id:
                    continue
                inv_date = str(_first_str(row, "Дата", "Date") or "")[:10]
                prev = headers.get(inv_id)
                if prev and prev.get("date", "") >= inv_date:
                    continue
                cp_id = _first_str(row, "Контрагент", "Контрагент_Key", "counterparty_id")
                cp_name = _first_str(
                    row,
                    "КонтрагентПредставление",
                    "counterparty_name",
                )
                if cp_name and cp_id:
                    self._counterparty_name_cache[cp_id.lower()] = cp_name
                header = headers[inv_id]
                if inv_date:
                    header["date"] = inv_date
                if cp_id:
                    header["counterparty_id"] = cp_id
                if cp_name:
                    header["counterparty_name"] = cp_name
                number = _first_str(row, "Номер", "Number")
                if number:
                    header["number"] = number
                if float(header.get("amount") or 0) <= 0:
                    doc_amount = _first_float(row, "СуммаДокумента", "Amount", "Сумма")
                    if doc_amount > 0:
                        header["amount"] = doc_amount

        orphan_links = set(lines_by_id.keys()) - {
            inv_id
            for inv_id, header in headers.items()
            if (header.get("counterparty_id") or "").strip()
        }
        if orphan_links:
            try:
                counterparties = self.get_counterparties(limit=50000)
            except Nova1CServiceError:
                counterparties = []
            cp_by_key = _orphan_invoice_counterparty_map(counterparties)
            orphan_cp_by_invoice: dict[str, str] = {}
            for inv_id in orphan_links:
                cp_id = cp_by_key.get((_guid_prefix7(inv_id), _guid_suffix(inv_id)))
                if not cp_id:
                    continue
                orphan_cp_by_invoice[inv_id] = cp_id
                cp_name = self._counterparty_name_cache.get(cp_id.lower(), "")
                header = headers[inv_id]
                header["counterparty_id"] = cp_id
                if cp_name:
                    header["counterparty_name"] = cp_name
            self._orphan_cp_by_invoice = orphan_cp_by_invoice

        self._invoice_lines_by_id = dict(lines_by_id)
        self._invoice_headers_by_id = headers

    def _normalize_payment_map_key(self, inv_id: str) -> str:
        lines = self._invoice_lines_by_id
        if lines:
            resolved = _resolve_invoice_line_key(inv_id, lines)
            if resolved:
                return _canonical_invoice_key(resolved)
        return _canonical_invoice_key(inv_id)

    def _lookup_batch_invoice(self, invoice_id: str) -> tuple[Optional[dict], list[dict]]:
        """Шапка и строки из batch-индекса (invoices/payments), если invoice_by_id пуст."""
        key = (invoice_id or "").strip()
        if not key:
            return None, []
        if self._invoice_headers_by_id is None or self._invoice_lines_by_id is None:
            try:
                self._ensure_invoice_index()
            except Nova1CServiceError:
                return None, []
        headers = self._invoice_headers_by_id or {}
        lines_map = self._invoice_lines_by_id or {}
        if key in headers:
            return dict(headers[key]), list(lines_map.get(key, []))
        target = _canonical_invoice_key(key)
        for inv_id, header in headers.items():
            if _canonical_invoice_key(inv_id) == target:
                return dict(header), list(lines_map.get(inv_id, []))
            if _invoice_keys_relaxed_match(inv_id, key):
                return dict(header), list(lines_map.get(inv_id, []))
        return None, []

    def lookup_batch_invoice_header(self, invoice_id: str) -> Optional[dict]:
        """Шапка счёта из batch invoices/payments (контрагент, сумма) — для post-sync в БД."""
        header, _ = self._lookup_batch_invoice(invoice_id)
        if not header:
            return None
        cp_name = (header.get("counterparty_name") or "").strip()
        cp_id = (header.get("counterparty_id") or "").strip()
        if not cp_name and not cp_id:
            return None
        amount = float(header.get("amount") or 0)
        return {
            "counterparty_id": cp_id,
            "counterparty_name": cp_name,
            "amount": amount,
        }

    def batch_invoice_headers_for_backfill(self) -> list[dict]:
        """Все шапки batch-индекса с контрагентом (для сопоставления по сумме)."""
        try:
            self._ensure_invoice_index()
        except Nova1CServiceError:
            return []
        headers = self._invoice_headers_by_id or {}
        out: list[dict] = []
        for inv_id, header in headers.items():
            cp_name = (header.get("counterparty_name") or "").strip()
            cp_id = (header.get("counterparty_id") or "").strip()
            if not cp_name and not cp_id:
                continue
            out.append(
                {
                    "invoice_id": inv_id,
                    "counterparty_id": cp_id,
                    "counterparty_name": cp_name,
                    "amount": float(header.get("amount") or 0),
                }
            )
        return out

    def _invoices_from_line_item_batch(self) -> List[Invoice]:
        self._ensure_invoice_index()
        assert self._invoice_headers_by_id is not None
        assert self._invoice_lines_by_id is not None
        invoices: list[Invoice] = []
        for inv_id, header in self._invoice_headers_by_id.items():
            items = self._invoice_lines_by_id.get(inv_id, [])
            amount = float(header.get("amount") or 0)
            invoices.append(
                Invoice.from_dict(
                    {
                        "id": inv_id,
                        "number": header.get("number") or "",
                        "date": header.get("date") or "",
                        "counterparty_id": header.get("counterparty_id") or "",
                        "counterparty_name": header.get("counterparty_name")
                        or self._counterparty_name_cache.get(
                            (header.get("counterparty_id") or "").lower(),
                            "",
                        ),
                        "amount": amount,
                        "currency": "KZT",
                        "status": "posted",
                        "items": items,
                    }
                )
            )
        return invoices

    def _counterparty_details_for_pdf(self, counterparty_id: str, tenant=None) -> dict:
        cp_key = (counterparty_id or "").strip().lower()
        if not cp_key:
            return {}
        tenant = self._resolve_tenant_for_pdf(tenant)
        if tenant and getattr(tenant, "id", None):
            try:
                from app.db.database import SessionLocal
                from app.services.counterparty_cache_service import find_counterparty_in_cache

                db = SessionLocal()
                try:
                    cached = find_counterparty_in_cache(db, tenant.id, cp_key)
                finally:
                    db.close()
                if cached:
                    phone = (cached.get("phoneNumber") or "").strip()
                    return {
                        "name": (cached.get("fullName") or "").strip(),
                        "bin": (cached.get("bin") or "").strip(),
                        "kbe": (cached.get("kbe") or "").strip(),
                        "address": (cached.get("address") or "").strip(),
                        "phone": phone,
                        "phones": [phone] if phone else [],
                    }
            except Exception as exc:
                logger.debug("Counterparty cache lookup for PDF failed: %s", exc)
        try:
            for cp in self.get_counterparties(limit=5000):
                if (cp.id or "").strip().lower() != cp_key:
                    continue
                phone = (cp.phone_number or cp.phone or "").strip()
                return {
                    "name": (cp.full_name or "").strip(),
                    "bin": (cp.bin or "").strip(),
                    "kbe": (cp.kbe or "").strip(),
                    "address": (cp.address or "").strip(),
                    "phone": phone,
                    "phones": [phone] if phone else [],
                }
        except Nova1CServiceError as exc:
            logger.debug("Counterparty lookup for PDF failed: %s", exc)
        return {}

    def _load_com_requisites_from_nova_script(self, uid_var: str) -> dict:
        """org + banks из Nova invoice_pdf (без MCP relay)."""
        if not self._script_ids.get("invoice_pdf"):
            return {}
        try:
            payload = self._run("invoice_pdf", vars={"uid": uid_var})
        except Nova1CServiceError as exc:
            logger.warning("COM requisites (invoice_pdf) failed: %s", exc)
            return {}
        results = (payload.get("result") or {}).get("results", {})
        return enrichment_from_script_results(results)

    def _load_odata_pdf_enrichment(self, invoice_id: str, tenant=None) -> dict:
        """
        OData (Moon/City): ИИК/БИК/банк/БИН/адрес из 1С, не из админки.
        Side-channel тем же логином, что и папки контрагентов.
        """
        if not invoice_id:
            return {}
        try:
            from app.services.counterparty_folder_enrichment import (
                _resolve_odata_sidechannel,
            )
            from app.services.odata_1c_client import OData1CClient
        except Exception as exc:
            logger.debug("OData PDF enrichment import failed: %s", exc)
            return {}

        side = _resolve_odata_sidechannel(tenant)
        if not side:
            logger.warning(
                "OData PDF enrichment: нет odata url/login у tenant (org=%s)",
                self._organization_id,
            )
            return {}

        odata_url, login, password = side
        client = None
        try:
            client = OData1CClient(
                base_url=odata_url,
                api_user=login,
                api_password=password,
                timeout=(10, 120),
            )
            if not client.access_token:
                client.authenticate()
            raw = client._build_invoice_pdf_payload(invoice_id)
        except Exception as exc:
            logger.warning(
                "OData PDF enrichment failed for %s: %s",
                invoice_id,
                exc,
            )
            return {}
        finally:
            try:
                if hasattr(client, "close"):
                    client.close()
            except Exception:
                pass

        if not raw:
            return {}

        enrichment: dict = {}
        for key in (
            "supplier_name",
            "supplier_bin",
            "supplier_kbe",
            "supplier_iik",
            "supplier_bik",
            "supplier_bank_name",
            "supplier_address",
            "payment_knp",
            "contract_text",
            "counterparty_bin",
            "counterparty_kbe",
            "counterparty_name",
            "counterparty_address",
            "counterparty_phone",
        ):
            val = raw.get(key)
            if val is not None and str(val).strip():
                enrichment[key] = str(val).strip()
        # полный buyer name из OData
        if raw.get("counterparty_name") and not enrichment.get("counterparty_name_full"):
            enrichment["counterparty_name_full"] = str(raw["counterparty_name"]).strip()
        phones = raw.get("supplier_phones")
        if isinstance(phones, list) and phones:
            enrichment["supplier_phones"] = phones
        if enrichment:
            logger.info(
                "OData PDF enrichment for %s: keys=%s",
                invoice_id,
                sorted(k for k in enrichment if k != "supplier_phones"),
            )
        return enrichment

    def _enrich_com_pdf_payload(
        self,
        invoice_id: str,
        header: Optional[dict],
        lines: list[dict],
        *,
        org: Optional[dict],
        tenant=None,
        script_results: Optional[dict] = None,
    ) -> Optional[dict]:
        uid_var = _nova_uid_var(invoice_id)
        cp_id = _first_str(header or {}, "Контрагент", "Контрагент_Key")

        script_enrich = enrichment_from_script_results(script_results or {})
        if script_enrich:
            merged_org = dict(org or {})
            for key, val in script_enrich.items():
                if key == "line_units" or val is None or not str(val).strip():
                    continue
                if not str(merged_org.get(key) or "").strip():
                    merged_org[key] = str(val).strip()
            org = merged_org

        # Реквизиты поставщика (ИИК/БИК/КБе/банк) меняются у арендатора почти
        # никогда и уже сохранены в админке (tenant.invoice_*) — подмешиваем
        # их сюда ДО живых походов в Nova, чтобы гейты ниже могли эти походы
        # пропустить, а не только использовать tenant как фоллбэк в конце.
        org = _merge_supplier_requisites(dict(org or {}), tenant)

        if not _pdf_payload_has_supplier_banks(org):
            extra = self._load_com_requisites_from_nova_script(uid_var)
            if extra:
                merged_org = dict(org or {})
                for key, val in extra.items():
                    if key == "line_units" or val is None or not str(val).strip():
                        continue
                    if not str(merged_org.get(key) or "").strip():
                        merged_org[key] = str(val).strip()
                org = merged_org

        enrichment: dict = dict(script_enrich) if script_enrich else {}
        # COM Maxi — MCP runScript, только если банков всё ещё нет (в т.ч. после
        # подстановки tenant.invoice_* выше) — раньше звонили сюда безусловно.
        if (
            self._agent_id
            and not self._odata_org
            and not _pdf_payload_has_supplier_banks(org)
        ):
            relay_enrich = fetch_com_pdf_enrichment(
                agent_id=self._agent_id,
                invoice_uid=invoice_id,
                uid_var=uid_var,
            )
            for key, val in relay_enrich.items():
                if val is not None and (key == "line_units" or str(val).strip()):
                    if key == "line_units" or not str(enrichment.get(key) or "").strip():
                        enrichment[key] = val

        # Moon/City OData: банки/БИН/адрес из 1С через OData (не админка)
        bank_probe = {**(org or {}), **enrichment}
        if self._odata_org and not _pdf_payload_has_supplier_banks(bank_probe):
            odata_enrich = self._load_odata_pdf_enrichment(invoice_id, tenant=tenant)
            for key, val in odata_enrich.items():
                if key == "supplier_phones":
                    if val and not enrichment.get(key):
                        enrichment[key] = val
                    continue
                if val is not None and str(val).strip():
                    if not str(enrichment.get(key) or "").strip():
                        enrichment[key] = val
                    if not str((org or {}).get(key) or "").strip():
                        org = dict(org or {})
                        org[key] = str(val).strip()

        cp_details = self._counterparty_details_for_pdf(cp_id, tenant=tenant)
        return _build_pdf_payload_from_nova_invoice(
            invoice_id,
            header,
            lines,
            org=org,
            tenant=tenant,
            enrichment=enrichment,
            counterparty=cp_details,
        )

    def _invoice_pdf_script_template(self) -> Optional[dict]:
        if self._invoice_pdf_script_body is not None:
            return self._invoice_pdf_script_body
        script_id = self._script_ids.get("invoice_pdf") or self._script_ids.get("invoice_by_id")
        if not script_id:
            return None
        try:
            payload = self._service._request(
                "GET",
                f"/api/v1/onec/scripts/{script_id}",
                params={"organization_id": self._organization_id},
            )
            body = payload.get("body") or {}
            if body.get("steps"):
                self._invoice_pdf_script_body = body
                return body
        except Nova1CServiceError as exc:
            logger.debug("Nova script body load failed: %s", exc)
        return None

    def _ensure_agent_id(self) -> None:
        """agent_id для MCP getpdf — без resolve_script_ids (не требует Nova admin login)."""
        if self._agent_lookup_done:
            return
        self._agent_lookup_done = True
        if self._agent_id:
            return
        try:
            cfg = self._service.get_org_config(self._organization_id)
            self._agent_id = (cfg.agent_id or "").strip() or None
            self._odata_org = bool((cfg.odata_url or "").strip())
        except Nova1CServiceError as exc:
            logger.warning(
                "Nova org %s: admin config unavailable (%s), MCP agent fallback",
                self._organization_id,
                exc,
            )
        if not self._agent_id:
            mapping = settings.NOVA_MCP_AGENT_BY_ORG or {}
            self._agent_id = (mapping.get(str(self._organization_id)) or "").strip() or None
            if self._agent_id and not self._odata_org:
                self._odata_org = True

    def _ensure_scripts(self) -> None:
        if self._script_ids:
            return
        self._ensure_agent_id()
        if self._script_ids_override:
            self._script_ids = dict(self._script_ids_override)
            # override может быть частичным (только явно заданные админом id) —
            # остальные ключи довосстанавливаем живым резолвом по имени скрипта
            # в Nova, а не молчим/падаем и не подставляем чужие номера.
            needed = {"invoices", "payments", "counterparties", "balance", "invoice_by_id", "invoice_pdf"}
            if needed - self._script_ids.keys():
                auto = self._service.resolve_script_ids(self._organization_id)
                for key, script_id in auto.items():
                    if not self._script_ids.get(key) and script_id:
                        self._script_ids[key] = script_id
        else:
            self._script_ids = self._service.resolve_script_ids(self._organization_id)
        if not self._agent_id:
            try:
                cfg = self._service.get_org_config(self._organization_id)
                self._agent_id = (cfg.agent_id or "").strip() or None
                self._odata_org = bool((cfg.odata_url or "").strip())
            except Nova1CServiceError as exc:
                logger.debug("Nova org config unavailable: %s", exc)
        if not self._script_ids.get("counterparties"):
            raise Nova1CServiceError(
                f"Nova org {self._organization_id}: script «Контрагенты» not found"
            )

    def _run(self, script_key: str, *, arguments: Optional[dict] = None, vars: Optional[dict] = None) -> dict:
        self._ensure_scripts()
        script_id = self._script_ids.get(script_key)
        if not script_id:
            raise Nova1CServiceError(
                f"Nova org {self._organization_id}: script «{script_key}» not found"
            )
        payload = self._service.run_script(
            self._organization_id,
            script_id,
            arguments=arguments,
            vars=vars,
        )
        if not payload.get("ok", True) and payload.get("error"):
            raise Nova1CServiceError(str(payload.get("error_message") or payload.get("error")))
        return payload

    def fetch_balance_by_counterparty(self) -> list[dict]:
        """
        onec.buh.balance → строки by_counterparty (debit/credit) + aging
        (долг по срокам) той же секцией того же ответа, смёрженные по
        counterparty_id — а где COM его не отдаёт вообще (только имя, как на
        org 119), по нормализованному имени, тем же приёмом, что и
        _resolve_missing_counterparty_ids ниже по цепочке для самого by_counterparty.
        Счета/платежи не трогаем — отдельный снимок для «кто реально должен».
        """
        self.authenticate()
        payload = self._run("balance")
        results = payload.get("result", {}).get("results", {})
        if not isinstance(results, dict):
            results = {}
        rows = _balance_rows_from_results(results)
        aging_rows = _aging_rows_from_results(results)
        aging_by_cp: dict[str, dict] = {}
        aging_by_name: dict[str, dict] = {}
        for row in aging_rows:
            if row.get("counterparty_id"):
                aging_by_cp[row["counterparty_id"]] = row
            name = normalize_counterparty_name(row.get("counterparty_name"))
            if name:
                aging_by_name[name] = row
        matched = 0
        if aging_by_cp or aging_by_name:
            for row in rows:
                aging = aging_by_cp.get(row.get("counterparty_id")) or aging_by_name.get(
                    normalize_counterparty_name(row.get("counterparty_name"))
                )
                if aging:
                    matched += 1
                    for key in (
                        "aging_current",
                        "aging_30",
                        "aging_60",
                        "aging_90",
                        "aging_over120",
                        "aging_unknown",
                        "aging_total",
                    ):
                        row[key] = aging.get(key)
        logger.info(
            "Nova balance by_counterparty: %s rows, %s aging rows, %s matched (org=%s)",
            len(rows),
            len(aging_rows),
            matched,
            self._organization_id,
        )
        return rows

    def get_counterparties(self, limit: int = 10000) -> List[Counterparty]:
        # Real incident 2026-09-02: get_1c_phones_for_counterparty (bulk
        # debtor mailing's phone fallback, invoice_access.py) calls this
        # with limit=50000 for EVERY counterparty that has no admin-entered
        # phone, just to find that one counterparty's own number — no
        # caching meant the WHOLE org's counterparty list (a live, full
        # 1C fetch, ~545 rows for this org) got re-fetched from scratch on
        # every one of 200+ rows in a single bulk run, the exact same
        # retry-storm shape as the earlier _ensure_invoice_index fix today,
        # just in a different function. Cached per client instance (one
        # instance per bulk run, via get_integration_for_tenant) — safe in
        # practice since every real caller's limit already exceeds any
        # org's actual counterparty count; a caller asking for fewer than
        # were cached still gets a correctly-sliced subset.
        if self._counterparties_cache is not None:
            return self._counterparties_cache[:limit]
        result = self._get_counterparties_uncached(limit)
        self._counterparties_cache = result
        return result

    def _get_counterparties_uncached(self, limit: int = 10000) -> List[Counterparty]:
        self.authenticate()
        # Аддитивно: parent в SELECT существующего скрипта counterparties (op не меняем).
        self._ensure_parent_on_counterparties_script()
        payload = self._run("counterparties")
        results = payload.get("result", {}).get("results", {})
        items = _counterparty_rows_from_results(results)
        phones_by_cp = _phones_by_counterparty_from_results(results)
        need_parent_map = not any((row.get("parent") or "").strip() for row in items[:20])
        parent_by_cp = self._counterparty_parent_map() if need_parent_map else {}
        if parent_by_cp:
            for row in items:
                cp_id = str(row.get("id") or "").strip().lower()
                meta = parent_by_cp.get(cp_id)
                if not meta:
                    continue
                if not (row.get("parent") or "").strip():
                    row["parent"] = meta.get("parent") or ""
        # Имя папки = fullName группы (скрипт counterparty_groups / fullName).
        if any((row.get("parent") or "").strip() for row in items):
            groups_by_id = {
                str(g.get("id") or "").strip().lower(): str(g.get("fullName") or "").strip()
                for g in self.get_counterparty_groups()
                if (g.get("id") or "").strip() and (g.get("fullName") or "").strip()
            }
            for row in items:
                if (row.get("folderName") or row.get("folder_name") or "").strip():
                    continue
                parent = str(row.get("parent") or "").strip().lower()
                if parent and not _is_empty_guid(parent) and parent in groups_by_id:
                    row["folderName"] = groups_by_id[parent]
        counterparties = [Counterparty.from_dict(row) for row in items[:limit]]
        _enrich_counterparties_phones(counterparties, phones_by_cp)
        for cp in counterparties:
            if cp.id and cp.full_name:
                self._counterparty_name_cache[cp.id.lower()] = cp.full_name.strip()
        if phones_by_cp:
            enriched = sum(
                1 for cp in counterparties if (cp.phone or cp.phone_number or "").strip()
            )
            logger.info(
                "Nova counterparties: %s rows, phones from contact info: %s/%s",
                len(counterparties),
                enriched,
                len(phones_by_cp),
            )
        with_folder = sum(1 for cp in counterparties if (cp.folder_name or "").strip())
        logger.info(
            "Nova counterparties: folderName filled for %s/%s",
            with_folder,
            len(counterparties),
        )
        return counterparties

    def _ensure_parent_on_counterparties_script(self) -> None:
        """Добавляет только `parent` в SELECT скрипта counterparties (без смены op/бизнес-логики)."""
        if getattr(self, "_parent_field_ensured", False):
            return
        self._parent_field_ensured = True
        self._ensure_scripts()
        script_id = self._script_ids.get("counterparties")
        if not script_id:
            return
        try:
            scripts = self._service.list_scripts(self._organization_id)
            script = next((s for s in scripts if int(s.get("ID") or 0) == int(script_id)), None)
            if not script:
                return
            body = script.get("body")
            if not isinstance(body, dict):
                return
            steps = body.get("steps")
            if not isinstance(steps, list) or not steps:
                return
            step = steps[0]
            if not isinstance(step, dict):
                return
            text = step.get("text") or ""
            if " КАК parent" in text:
                return
            needle = "Контрагенты.Наименование КАК fullName"
            if needle not in text:
                return
            insert = (
                "Контрагенты.Наименование КАК fullName, "
                "УНИКАЛЬНЫЙИДЕНТИФИКАТОР(Контрагенты.Родитель) КАК parent"
            )
            new_text = text.replace(needle, insert, 1)
            if new_text == text:
                return
            new_body = dict(body)
            new_steps = list(steps)
            new_step = dict(step)
            new_step["text"] = new_text
            new_steps[0] = new_step
            new_body["steps"] = new_steps
            self._service.update_script(
                self._organization_id,
                int(script_id),
                body=new_body,
            )
            logger.info(
                "Nova org %s: counterparties script %s enriched with parent",
                self._organization_id,
                script_id,
            )
        except Exception as exc:
            logger.warning(
                "Nova org %s: could not enrich counterparties script with parent: %s",
                self._organization_id,
                exc,
            )

    def get_counterparty_groups(self) -> list[dict]:
        """Папки справочника Контрагенты: id, fullName, parent, folderType."""
        self.authenticate()
        self._ensure_scripts()
        script_id = self._script_ids.get("counterparty_groups")
        if not script_id:
            scripts = self._service.list_scripts(self._organization_id)
            script_id = self._service.find_script_id(scripts, "групп", "контрагент")
            if script_id is None:
                script_id = self._service.find_script_id(scripts, "групп")
            if script_id is not None:
                self._script_ids["counterparty_groups"] = script_id
        if not script_id:
            return []
        payload = self._service.run_script(self._organization_id, int(script_id))
        if not payload.get("ok", True) and payload.get("error"):
            raise Nova1CServiceError(str(payload.get("error_message") or payload.get("error")))
        results = payload.get("result", {}).get("results", {})
        rows = _group_rows_from_results(results)
        out: list[dict] = []
        for row in rows:
            full_name = str(row.get("fullName") or "").strip()
            if not full_name:
                continue
            out.append(
                {
                    "id": str(row.get("id") or "").strip(),
                    "fullName": full_name,
                    "parent": str(row.get("parent") or "").strip(),
                    "folderType": True,
                    "code": str(row.get("code") or "").strip(),
                }
            )
        return out

    def _counterparty_parent_map(self) -> dict[str, dict[str, str]]:
        """id(lower) → {parent, folderName}; отдельный скрипт, BUH: Контрагенты не меняем."""
        try:
            created = self._service.upsert_script_by_name(
                self._organization_id,
                name=_COUNTERPARTY_PARENT_SCRIPT_NAME,
                description=(
                    "Карта родительской папки контрагента (parent/folderName) для фильтра на портале"
                ),
                body=_COUNTERPARTY_PARENT_SCRIPT_BODY,
            )
            script_id = int(created.get("ID") or created.get("id") or 0)
            if script_id < 1:
                scripts = self._service.list_scripts(self._organization_id)
                for script in scripts:
                    if (script.get("name") or "").strip() == _COUNTERPARTY_PARENT_SCRIPT_NAME:
                        script_id = int(script["ID"])
                        break
            if script_id < 1:
                return {}
            payload = self._service.run_script(self._organization_id, script_id)
            if not payload.get("ok", True) and payload.get("error"):
                logger.warning(
                    "Nova parent/folder map failed org=%s: %s",
                    self._organization_id,
                    payload.get("error_message") or payload.get("error"),
                )
                return {}
            results = payload.get("result", {}).get("results", {})
            mapping: dict[str, dict[str, str]] = {}
            for row in _parent_rows_from_results(results):
                cp_id = str(row.get("id") or "").strip().lower()
                if not cp_id:
                    continue
                parent = str(row.get("parent") or "").strip()
                folder_name = str(row.get("folderName") or "").strip()
                if _is_empty_guid(parent):
                    parent = ""
                    folder_name = ""
                mapping[cp_id] = {"parent": parent, "folderName": folder_name}
            return mapping
        except Exception as exc:
            logger.warning(
                "Nova parent/folder map unavailable org=%s: %s",
                self._organization_id,
                exc,
            )
            return {}

    def get_contracts_by_counterparty(self) -> dict[str, list[dict]]:
        return {}

    def get_invoice_counts_by_counterparty(self) -> dict[str, int]:
        self._ensure_invoice_index()
        counts: dict[str, int] = {}
        headers = self._invoice_headers_by_id or {}
        for inv_id, header in headers.items():
            cp_key = (header.get("counterparty_id") or "").strip().lower()
            if not cp_key and self._orphan_cp_by_invoice:
                cp_key = (self._orphan_cp_by_invoice.get(inv_id) or "").strip().lower()
            if cp_key:
                counts[cp_key] = counts.get(cp_key, 0) + 1
        return counts

    def _invoice_due_dates(
        self,
        invoice_date: date,
        rent_due_day: int,
        utilities_due_day: int,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> tuple[date, date, date]:
        ops_day = operations_due_day if operations_due_day is not None else rent_due_day
        if period and len(period) == 7 and period[4] == "-":
            try:
                year, month = int(period[:4]), int(period[5:7])
                last = calendar.monthrange(year, month)[1]
                rent = date(year, month, min(max(1, rent_due_day), last))
                util = date(year, month, min(max(1, utilities_due_day), last))
                ops = date(year, month, min(max(1, ops_day), last))
                # Срок в месяце периода корректен только когда счёт датирован
                # заранее (аренда за июль часто датируется концом июня) — но
                # период нередко совпадает с месяцем самого счёта (счёт от
                # 20.08 в периоде "2026-08"), и тогда "5-е число периода"
                # оказывается РАНЬШЕ даты счёта. Такой срок недействителен —
                # переносим на следующий месяц после даты счёта.
                if rent <= invoice_date:
                    rent = _calculate_due_date(invoice_date, rent_due_day)
                if util <= invoice_date:
                    util = _calculate_due_date(invoice_date, utilities_due_day)
                if ops <= invoice_date:
                    ops = _calculate_due_date(invoice_date, ops_day)
                return rent, util, ops
            except ValueError:
                pass
        return (
            _calculate_due_date(invoice_date, rent_due_day),
            _calculate_due_date(invoice_date, utilities_due_day),
            _calculate_due_date(invoice_date, ops_day),
        )

    def _load_payments_by_invoice_id(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> dict[str, list]:
        if not self._script_ids.get("payments"):
            try:
                self._ensure_scripts()
            except Nova1CServiceError:
                return {}
        if not self._script_ids.get("payments"):
            return {}

        vars_payload: dict[str, str] = {}
        if since:
            vars_payload["since"] = str(since).split("T")[0]
        if until:
            vars_payload["until"] = str(until).split("T")[0]
        try:
            payload = self._run("payments", vars=vars_payload or None)
        except Nova1CServiceError as exc:
            logger.debug("Nova payments script failed: %s", exc)
            return {}

        rows = _extract_batch_items(payload.get("result", {}).get("results", {}))
        payments: dict[str, list] = {}
        since_day = str(since).split("T")[0] if since else None
        until_day = str(until).split("T")[0] if until else None
        try:
            self._ensure_invoice_index()
        except Nova1CServiceError:
            pass
        for row in rows:
            inv_id = _first_str(
                row,
                "СчетНаОплату",
                "СчетНаОплатуПокупателю_Key",
                "СчетНаОплату_Key",
                "ДокументОснование",
                "ДокументОснование_Key",
            )
            if not inv_id or inv_id == _EMPTY_INVOICE_GUID:
                continue
            key = self._normalize_payment_map_key(inv_id)
            if not key:
                continue
            pay_date = _first_str(row, "Дата", "Date", "ДатаВыписки")
            if since_day or until_day:
                parsed_pay = _parse_date_value(pay_date or "")
                if parsed_pay:
                    pay_day = parsed_pay.isoformat()
                    if since_day and pay_day < since_day:
                        continue
                    if until_day and pay_day > until_day:
                        continue
            amount = _first_float(
                row,
                "СуммаОборот",
                "СуммаДокумента",
                "Сумма",
                "Amount",
                "paid_amount",
            )
            payments.setdefault(key, []).append(
                {"amount": amount or 0.0, "date": pay_date}
            )
        if payments:
            logger.debug("Nova: payments linked to %s invoices", len(payments))
        return payments

    def _fetch_payments_linked_to_invoice(
        self,
        invoice_id: str,
        *,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> list[dict]:
        """Платежи, привязанные к одному счёту (для live-проверки COM)."""
        target_key = _canonical_invoice_key(invoice_id)
        if not target_key:
            return []
        if not self._script_ids.get("payments"):
            try:
                self._ensure_scripts()
            except Nova1CServiceError:
                return []
        if not self._script_ids.get("payments"):
            return []

        vars_payload: dict[str, str] = {}
        if since:
            vars_payload["since"] = str(since).split("T")[0]
        if until:
            vars_payload["until"] = str(until).split("T")[0]
        try:
            payload = self._run("payments", vars=vars_payload or None)
        except Nova1CServiceError as exc:
            logger.debug("Nova payments for invoice %s failed: %s", invoice_id, exc)
            return []

        rows = _extract_batch_items(payload.get("result", {}).get("results", {}))
        linked: list[dict] = []
        since_day = str(since).split("T")[0] if since else None
        until_day = str(until).split("T")[0] if until else None
        for row in rows:
            inv_id = _first_str(
                row,
                "СчетНаОплату",
                "СчетНаОплатуПокупателю_Key",
                "СчетНаОплату_Key",
                "ДокументОснование",
                "ДокументОснование_Key",
            )
            if not inv_id or inv_id == _EMPTY_INVOICE_GUID:
                continue
            if not (
                _canonical_invoice_key(inv_id) == target_key
                or _invoice_keys_relaxed_match(inv_id, target_key)
            ):
                continue
            pay_date = _first_str(row, "Дата", "Date", "ДатаВыписки")
            if since_day or until_day:
                parsed_pay = _parse_date_value(pay_date or "")
                if parsed_pay:
                    pay_day = parsed_pay.isoformat()
                    if since_day and pay_day < since_day:
                        continue
                    if until_day and pay_day > until_day:
                        continue
            amount = _first_float(
                row,
                "СуммаОборот",
                "СуммаДокумента",
                "Сумма",
                "Amount",
                "paid_amount",
            )
            linked.append({"amount": amount or 0.0, "date": pay_date})
        return linked

    def _resolve_payment_status(
        self,
        invoice_amount: float,
        invoice_date_str: str,
        payments: list,
        due_day: int = 5,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
        invoice_items: Optional[list] = None,
    ) -> tuple[str, Optional[str], float]:
        total_paid = sum(float(p.get("amount") or 0) for p in payments)
        paid_dates = [
            _parse_date_value(p.get("date") or "")
            for p in payments
            if p.get("date")
        ]
        paid_dates = [d for d in paid_dates if d]
        paid_at = max(paid_dates).isoformat() if paid_dates else None

        amount = float(invoice_amount or 0)
        if paid_enough(amount, total_paid):
            return "paid", paid_at, total_paid

        inv_date = _parse_date_value(invoice_date_str)
        if inv_date:
            util_day = utilities_due_day if utilities_due_day is not None else due_day
            ops_day = operations_due_day if operations_due_day is not None else due_day
            rent_due, util_due, ops_due = self._invoice_due_dates(
                inv_date, due_day, util_day, ops_day, period
            )
            today = date.today()
            service_types = resolve_invoice_service_types(invoice_items or [])
            if len(service_types) == 1:
                st = service_types[0]
                applicable = due_date_in_invoice_month(
                    inv_date,
                    due_day_for_service_type(
                        st,
                        rent=due_day,
                        utilities=util_day,
                        operations=ops_day,
                    ),
                )
                if today > applicable:
                    return "overdue", paid_at, total_paid
            elif today > util_due or today > rent_due or today > ops_due:
                return "overdue", paid_at, total_paid

        # Не просрочен, но что-то уже поступило — "partial", не "unpaid".
        # Просрочка (выше) важнее: частично оплаченный, но просроченный счёт
        # остаётся overdue, а не превращается в partial.
        if total_paid > 0:
            return "partial", paid_at, total_paid
        return "unpaid", paid_at, total_paid

    def _enrich_invoices_payment_status(
        self,
        invoices: List[Invoice],
        due_day: int = 5,
        payment_since: Optional[str] = None,
        payment_until: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> List[Invoice]:
        if not invoices:
            return invoices
        payments_map = self._load_payments_by_invoice_id(
            since=payment_since,
            until=payment_until,
        )
        paid_count = 0
        for inv in invoices:
            linked = _payments_for_invoice(payments_map, inv.id or "")
            # Явный СтатусОплаты из 1С (paid/unpaid/overdue) — не пересчитывать по due_date.
            explicit = str(inv.payment_status or "").lower().strip()
            if explicit in ("paid", "unpaid", "overdue"):
                pay_status = explicit
                if linked:
                    total_paid = sum(float(p.get("amount") or 0) for p in linked)
                    paid_dates = [
                        _parse_date_value(p.get("date") or "")
                        for p in linked
                        if p.get("date")
                    ]
                    paid_dates = [d for d in paid_dates if d]
                    paid_at = (
                        max(paid_dates).isoformat() if paid_dates else inv.paid_at
                    )
                else:
                    total_paid = float(inv.paid_amount or 0)
                    paid_at = inv.paid_at
                if pay_status == "paid" and total_paid <= 0:
                    total_paid = float(inv.paid_amount or inv.amount or 0)
                # СтатусОплаты из скрипта invoices иногда расходится с реальными
                # привязанными платежами (org 127: "unpaid" при найденном платеже
                # на полную сумму — см. BUH-API-reference vs onec.buh.payments
                # живьём). Привязанный платёж, покрывающий счёт, — надёжнее
                # самоотчёта скрипта: не оставляем клиента с "unpaid" в статусе,
                # если оплата фактически найдена.
                if pay_status != "paid" and linked and paid_enough(float(inv.amount or 0), total_paid):
                    pay_status = "paid"
            elif linked:
                pay_status, paid_at, total_paid = self._resolve_payment_status(
                    inv.amount,
                    inv.date,
                    linked,
                    due_day,
                    utilities_due_day=utilities_due_day,
                    operations_due_day=operations_due_day,
                    period=period,
                    invoice_items=inv.items,
                )
            elif float(inv.paid_amount or 0) > 0 and float(inv.amount or 0) > 0:
                # Сумма оплаты уже известна из заголовка счёта (нет отдельных
                # связанных платёжных документов) — используем её напрямую,
                # не теряем частичную оплату, подставляя total_paid=0 через
                # _resolve_payment_status([], ...).
                total_paid = float(inv.paid_amount or 0)
                paid_at = inv.paid_at
                if paid_enough(float(inv.amount or 0), total_paid):
                    pay_status = "paid"
                else:
                    due_status, _, _ = self._resolve_payment_status(
                        inv.amount,
                        inv.date,
                        [],
                        due_day,
                        utilities_due_day=utilities_due_day,
                        operations_due_day=operations_due_day,
                        period=period,
                        invoice_items=inv.items,
                    )
                    pay_status = "overdue" if due_status == "overdue" else "partial"
            else:
                pay_status, paid_at, total_paid = self._resolve_payment_status(
                    inv.amount,
                    inv.date,
                    [],
                    due_day,
                    utilities_due_day=utilities_due_day,
                    operations_due_day=operations_due_day,
                    period=period,
                    invoice_items=inv.items,
                )
            inv.payment_status = pay_status
            inv.paid_at = paid_at
            inv.paid_amount = total_paid if total_paid > 0 else None
            inv_date = _parse_date_value(inv.date)
            if inv_date:
                util_day = utilities_due_day if utilities_due_day is not None else due_day
                ops_day = operations_due_day if operations_due_day is not None else due_day
                service_types = resolve_invoice_service_types(inv.items or [])
                if len(service_types) == 1:
                    day = due_day_for_service_type(
                        service_types[0],
                        rent=due_day,
                        utilities=util_day,
                        operations=ops_day,
                    )
                    inv.due_date = due_date_in_invoice_month(inv_date, day).isoformat()
                else:
                    rent_due, _, _ = self._invoice_due_dates(
                        inv_date, due_day, util_day, ops_day, period
                    )
                    inv.due_date = rent_due.isoformat()
            if pay_status == "paid":
                paid_count += 1
        logger.debug(
            "Nova: payment status — paid %s, total invoices %s",
            paid_count,
            len(invoices),
        )
        return invoices

    def get_invoices(
        self,
        since: Union[str, datetime] = None,
        until: Union[str, datetime] = None,
        limit: int = 10000,
        due_day: int = 5,
        enrich_payment_status: bool = True,
        payment_since: Optional[str] = None,
        payment_until: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> List[Invoice]:
        self.authenticate()
        vars_payload: dict = {}
        if since:
            since_day = since.strftime("%Y-%m-%d") if isinstance(since, datetime) else str(since)[:10]
            vars_payload["since"] = since_day
        payload = self._run("invoices", vars=vars_payload or None)
        results = payload.get("result", {}).get("results", {})
        header_rows = _extract_invoice_header_items(results)
        line_rows = _extract_invoice_line_items_batch(results)
        rows = header_rows or _extract_batch_items(results)
        if _is_line_item_batch(rows):
            index_rows = rows
            if not index_rows and vars_payload.get("since"):
                full_results = self._run("invoices").get("result", {}).get("results", {})
                index_rows = _extract_batch_items(full_results)
            self._ensure_invoice_index(line_rows=index_rows)
            invoices = self._invoices_from_line_item_batch()
        elif not rows:
            full_results = self._run("invoices").get("result", {}).get("results", {})
            full_header_rows = _extract_invoice_header_items(full_results)
            full_line_rows = _extract_invoice_line_items_batch(full_results)
            full_rows = full_header_rows or _extract_batch_items(full_results)
            if _is_line_item_batch(full_rows):
                self._ensure_invoice_index(line_rows=full_rows)
                invoices = self._invoices_from_line_item_batch()
            else:
                if full_header_rows:
                    invoices = [_nova_row_to_invoice(row) for row in full_header_rows]
                    line_rows = full_line_rows
                else:
                    invoices = []
        else:
            invoices = [_nova_row_to_invoice(row) for row in rows]

        # For invoice header batch, attach detailed line items by invoice id.
        if invoices and line_rows and not _is_line_item_batch(rows):
            lines_by_id: dict[str, list[dict]] = defaultdict(list)
            for row in line_rows:
                link = _first_str(row, "Ссылка", "Ref_Key", "Ref", "id", "СчетНаОплату")
                name = _line_item_name(row)
                if link and name:
                    lines_by_id[link].append(
                        {
                            "name": name,
                            "amount": _first_float(row, "Сумма", "amount"),
                        }
                    )
            if lines_by_id:
                for inv in invoices:
                    if inv.id and lines_by_id.get(inv.id):
                        inv.items = list(lines_by_id[inv.id])

        since_day = None
        until_day = None
        if since:
            since_day = since.strftime("%Y-%m-%d") if isinstance(since, datetime) else str(since)[:10]
        if until:
            until_day = until.strftime("%Y-%m-%d") if isinstance(until, datetime) else str(until)[:10]
        if since_day or until_day:
            filtered: list[Invoice] = []
            for inv in invoices:
                inv_day = (inv.date or "")[:10]
                if not inv_day:
                    if period and self._invoice_belongs_to_period(inv.date, inv.due_date, period):
                        filtered.append(inv)
                    continue
                if since_day and inv_day < since_day:
                    continue
                if until_day and inv_day > until_day:
                    continue
                filtered.append(inv)
            invoices = filtered

        if limit and len(invoices) > limit:
            invoices = invoices[:limit]

        if enrich_payment_status:
            return self._enrich_invoices_payment_status(
                invoices,
                due_day=due_day,
                payment_since=payment_since,
                payment_until=payment_until,
                utilities_due_day=utilities_due_day,
                operations_due_day=operations_due_day,
                period=period,
            )
        return invoices

    def fetch_invoice_line_items(self, invoice_id: str) -> List[dict]:
        if not invoice_id:
            return []
        key = invoice_id.strip()
        if self._invoice_lines_by_id is not None:
            cached = self._invoice_lines_by_id.get(key)
            if cached:
                return list(cached)
        try:
            self._ensure_invoice_index()
            if self._invoice_lines_by_id:
                cached = self._invoice_lines_by_id.get(key)
                if cached:
                    return list(cached)
        except Exception:
            # Real incident 2026-09-02: a slow/broken Nova org (Maxi Mall)
            # made _ensure_invoice_index's two full-org fetches (up to 120s
            # each) fail/time out. _ensure_invoice_index itself only marks
            # "already tried" on SUCCESS (see its own docstring/callers —
            # deliberately still raises on failure for
            # get_invoice_counterparty_id's own error-vs-not-found
            # distinction, so that contract stays untouched here), so
            # without this, every subsequent invoice in a bulk loop (e.g.
            # bulk_debtor_notify_service, one call per invoice) retried the
            # same ~240s round trip from scratch — on 130+ rows the
            # background job could run for hours without completing a
            # single one. Negative-cache here instead, local to this one
            # heavily-looped call site: pay the retry cost once per
            # process, not once per invoice. Catches bare Exception, not
            # just Nova1CServiceError — a raw requests timeout/connection
            # error from the underlying HTTP call is not guaranteed to be
            # wrapped by the time it gets here.
            if self._invoice_lines_by_id is None:
                self._invoice_lines_by_id = {}
            if self._invoice_headers_by_id is None:
                self._invoice_headers_by_id = {}
        try:
            payload = self._run("invoice_by_id", vars={"uid": _nova_uid_var(invoice_id)})
        except Exception as exc:
            logger.debug("Nova invoice_by_id failed for %s: %s", invoice_id, exc)
            return []
        results = payload.get("result", {}).get("results", {})
        _, lines = _invoice_by_id_sections(results)
        if lines:
            return _normalize_line_items(lines)
        return _extract_line_items_from_results(results)

    def fetch_invoice_payment_status(
        self,
        invoice_id: str,
        *,
        due_day: int = 5,
        payment_since: Optional[str] = None,
        payment_until: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> Optional[Invoice]:
        """Live-проверка одного счёта: invoice_by_id, при пустом ответе — batch-индекс."""
        key = (invoice_id or "").strip()
        if not key:
            return None
        self.authenticate()
        header: Optional[dict] = None
        lines: list[dict] = []
        script_error: Optional[str] = None
        try:
            payload = self._run("invoice_by_id", vars={"uid": _nova_uid_var(key)})
            results = payload.get("result", {}).get("results", {})
            header, lines = _invoice_by_id_sections(results)
            if not header:
                invoice = results.get("invoice")
                if isinstance(invoice, dict):
                    header = invoice
        except Nova1CServiceError as exc:
            script_error = str(exc)
            logger.warning("Nova live invoice check failed for %s: %s", key, exc)

        if not header:
            batch_header, batch_lines = self._lookup_batch_invoice(key)
            if batch_header:
                header, lines = batch_header, batch_lines
                logger.info(
                    "Nova live invoice check: batch index for %s (script=%s)",
                    key,
                    "empty" if not script_error else "failed",
                )

        if not header:
            return None
        inv = _nova_header_to_invoice(key, header, lines)
        if str(inv.payment_status or "").lower() == "paid":
            return inv
        amount = float(inv.amount or 0)
        paid_header = float(inv.paid_amount or 0)
        if paid_enough(amount, paid_header):
            inv.payment_status = "paid"
            inv.paid_amount = paid_header
            return inv

        linked = self._fetch_payments_linked_to_invoice(
            key,
            since=payment_since,
            until=payment_until,
        )
        if not linked:
            linked = self._fetch_payments_linked_to_invoice(key)

        pay_status, paid_at, total_paid = self._resolve_payment_status(
            inv.amount,
            inv.date,
            linked,
            due_day,
            utilities_due_day=utilities_due_day,
            operations_due_day=operations_due_day,
            period=period,
            invoice_items=inv.items,
        )
        inv.payment_status = pay_status
        inv.paid_at = paid_at
        inv.paid_amount = total_paid if total_paid > 0 else inv.paid_amount
        if pay_status == "paid":
            logger.info(
                "Nova live invoice check: paid invoice=%s paid=%s amount=%s",
                key,
                inv.paid_amount,
                inv.amount,
            )
        return inv

    def get_invoice_counterparty_id(self, invoice_id: str) -> Optional[str]:
        """None — 1С реально не знает такой счёт. Nova1CServiceError —
        не смогли спросить вообще (сеть/логин/etc), это ДРУГОЙ случай, не
        "не найден", и вызывающий код (assert_invoice_belongs_to_counterparty)
        не должен его путать с настоящим 404 (реальный инцидент 2026-08-31:
        "Неверный логин или пароль пользователя 1С" на ЛЮБОМ скрипте этой
        организации молча превращался тут в None, а выше — в ложное "Счёт
        не найден в 1С" вместо честного 503 с настоящей причиной).

        Всё равно пробуем оба способа по очереди, даже если первый упал с
        ошибкой — разные организации отдают разную форму ответа (см.
        nova_1c_scripts_audit), второй иногда срабатывает там, где первый
        скрипт просто не настроен для этой организации, а не потому что 1С
        недоступна целиком. Поднимаем исключение только если ОБА способа не
        дали результата И хотя бы один из них реально упал (не просто "нет
        данных")."""
        key = (invoice_id or "").strip()
        if self._invoice_headers_by_id:
            if key in self._invoice_headers_by_id:
                return self._invoice_headers_by_id[key].get("counterparty_id")
            target = _canonical_invoice_key(key)
            for inv_id, header in self._invoice_headers_by_id.items():
                if _canonical_invoice_key(inv_id) == target or _invoice_keys_relaxed_match(inv_id, key):
                    return (header or {}).get("counterparty_id")

        last_error: Optional[Nova1CServiceError] = None

        try:
            payload = self._run("invoice_by_id", vars={"uid": _nova_uid_var(invoice_id)})
        except Nova1CServiceError as exc:
            last_error = exc
            payload = None
        if payload:
            results = payload.get("result", {}).get("results", {})
            header, _ = _invoice_by_id_sections(results)
            if header:
                cp_id = _first_str(header, "Контрагент", "Контрагент_Key")
                if cp_id:
                    return cp_id
            invoice = results.get("invoice")
            if isinstance(invoice, dict):
                cp_id = _first_str(
                    invoice,
                    "counterparty_id",
                    "Контрагент_Key",
                    "Контрагент",
                )
                if cp_id:
                    return cp_id
        try:
            self._ensure_invoice_index()
            if self._invoice_headers_by_id:
                if key in self._invoice_headers_by_id:
                    return self._invoice_headers_by_id[key].get("counterparty_id")
                target = _canonical_invoice_key(key)
                for inv_id, header in self._invoice_headers_by_id.items():
                    if _canonical_invoice_key(inv_id) == target or _invoice_keys_relaxed_match(inv_id, key):
                        return (header or {}).get("counterparty_id")
        except Nova1CServiceError as exc:
            last_error = exc

        if last_error:
            raise last_error
        return None

    def _resolve_tenant_for_pdf(self, tenant=None):
        if tenant is not None:
            return tenant
        try:
            from app.db.database import SessionLocal
            from app.models.catalog import Tenant

            db = SessionLocal()
            try:
                return (
                    db.query(Tenant)
                    .filter(
                        Tenant.nova_organization_id == self._organization_id,
                        Tenant.is_active.is_(True),
                    )
                    .first()
                )
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Nova: tenant for PDF stamp/signature not resolved: %s", exc)
            return None

    def download_invoice_file(
        self,
        invoice_id: str,
        pdf_path: Optional[str] = None,
        save_path: Optional[str] = None,
        tenant=None,
        force: bool = False,
    ) -> Optional[str]:
        tenant = self._resolve_tenant_for_pdf(tenant)
        if not invoice_id:
            return None

        if save_path is None:
            save_path = str(_resolve_downloads_path(invoice_id))
        else:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.suffix.lower() != ".pdf":
                save_path = str(out.with_suffix(".pdf"))

        out = Path(save_path)

        # Кэш структурированных данных счёта — быстрее и не трогает 1С
        # вообще, в отличие от кэша готовых PDF-байт ниже (тот всё равно
        # требует один живой fetch каждые _PDF_CACHE_MAX_AGE=7 дней). См.
        # app/services/invoice_pdf_cache.py — реквизиты поставщика в
        # закэшированном payload'е нет, get_cached_payload сама подмешивает
        # их из ТЕКУЩЕЙ записи tenant, поэтому это не тот же риск
        # устаревания, что уже был у файлового кэша ниже.
        #
        # Строки/суммы теперь тоже не застывают навечно — get_cached_payload
        # отдаёт None и на "просрочку" (LINE_ITEMS_FRESHNESS_TTL), не только
        # на полное отсутствие кэша (см. баг 2026-09-14, Astranium). Но сам
        # по себе просроченный payload-кэш недостаточен: файловый PDF-кэш
        # ниже перезаписывается КАЖДЫМ payload-cache-hit'ом (см. ветку ниже),
        # то есть его mtime всегда "только что" и он молча замаскирует нужное
        # обновление, минуя живую 1С вообще. Поэтому при именно просрочке (а
        # не при обычном "кэша не было") инвалидируем и его тоже.
        if not force and tenant is not None:
            from app.db.database import SessionLocal
            from app.services.invoice_pdf_cache import (
                LINE_ITEMS_FRESHNESS_TTL,
                get_cached_payload,
                is_payload_cache_stale,
            )

            cache_db = SessionLocal()
            try:
                cached_payload = get_cached_payload(cache_db, tenant, invoice_id)
                payload_cache_expired = (
                    not cached_payload
                    and is_payload_cache_stale(cache_db, tenant.id, invoice_id)
                )
            finally:
                cache_db.close()
            if payload_cache_expired:
                logger.info(
                    "Nova: закэшированный payload для %s просрочен (>%s) — "
                    "инвалидируем и файловый PDF-кэш, идём в живую 1С",
                    invoice_id,
                    LINE_ITEMS_FRESHNESS_TTL,
                )
                if out.exists():
                    out.unlink()
                _pdf_cache_meta_path(out).unlink(missing_ok=True)
            if cached_payload:
                if not _pdf_payload_has_supplier_banks(cached_payload):
                    tenant_label = (
                        getattr(tenant, "legal_name", None)
                        or getattr(tenant, "name", None)
                        or f"tenant_id={self._organization_id}"
                    )
                    raise MissingSupplierRequisitesError(
                        f"У «{tenant_label}» не заполнены банковские реквизиты поставщика "
                        "(ИИК/БИК/банк) — ни в 1С, ни в резервных полях. Заполните ИИК/БИК/Банк "
                        "бенефициара в карточке арендатора в админке (раздел «Реквизиты счёта»), "
                        "чтобы сформировать PDF счёта."
                    )
                from app.services.invoice_report import generate_formal_invoice_document

                generated = generate_formal_invoice_document(cached_payload, str(out), tenant)
                if generated and Path(generated).is_file():
                    logger.info(
                        "Nova: PDF счёта %s из кэша структурированных данных (%s bytes)",
                        invoice_id,
                        Path(generated).stat().st_size,
                    )
                    return str(Path(generated).resolve())
                # Рендер из кэша не удался (например, испортился шаблон) —
                # не сдаёмся, продолжаем обычным живым путём ниже.
                logger.warning(
                    "Nova: рендер из кэша payload'а не удался для %s — живой путь", invoice_id
                )

        cached_pdf = None if force else _try_reuse_cached_pdf(
            out,
            invoice_id,
            # без ИИК/БИК в meta — пересобрать (OData теперь тянет из 1С)
            require_supplier_banks=True,
        )
        if cached_pdf:
            return cached_pdf
        if force:
            logger.info("Nova: force-refresh PDF для %s — кэш игнорируется", invoice_id)
        if out.exists():
            out.unlink()
        _pdf_cache_meta_path(out).unlink(missing_ok=True)

        last_error: Optional[str] = None
        # голый PDF из 1С — только запасной, если портал не собрался
        native_pdf_fallback: Optional[bytes] = None

        def _write_pdf_bytes(pdf_bytes: bytes, source: str) -> str:
            out.write_bytes(pdf_bytes)
            logger.info(
                "Nova %s: печатная форма 1С для счёта %s (%s bytes)",
                source,
                invoice_id,
                len(pdf_bytes),
            )
            return str(out.resolve())

        self._ensure_agent_id()
        # OData getpdf часто даёт пустой бланк без поставщика/печати — не возвращаем сразу.
        if self._agent_id and relay_configured() and self._odata_org:
            try:
                b64_pdf = call_buh_getpdf(
                    agent_id=self._agent_id,
                    invoice_uid=invoice_id,
                )
                if b64_pdf:
                    pdf_bytes = _extract_pdf_from_value(b64_pdf)
                    if pdf_bytes:
                        native_pdf_fallback = pdf_bytes
                        logger.info(
                            "Nova OData: getpdf есть (%s bytes), сначала пробуем портальный макет",
                            len(pdf_bytes),
                        )
                    else:
                        last_error = "onec.buh.getpdf: base64 не является валидным PDF"
            except NovaMcpRelayError as exc:
                last_error = str(exc)
                logger.warning("Nova MCP getpdf for %s: %s", invoice_id, exc)

        self._ensure_scripts()

        script_keys = []
        if self._script_ids.get("invoice_pdf"):
            script_keys.append("invoice_pdf")
        if self._script_ids.get("invoice_by_id"):
            script_keys.append("invoice_by_id")
        if not self._odata_org:
            # invoice_pdf содержит шаг org (ИИК/БИК/КНП); invoice_by_id — только batch.
            com_keys = [k for k in ("invoice_pdf", "invoice_by_id") if k in script_keys]
            if com_keys:
                script_keys = com_keys

        invoice_payload: Optional[dict] = None
        uid_var = _nova_uid_var(invoice_id)
        for script_key in script_keys:
            try:
                payload = self._run(script_key, vars={"uid": uid_var})
            except Nova1CServiceError as exc:
                last_error = str(exc)
                logger.debug("Nova %s failed for %s: %s", script_key, invoice_id, exc)
                continue

            if payload.get("ok") is False:
                last_error = str(payload.get("error_message") or payload.get("error") or "script failed")
                continue

            result = payload.get("result") or {}
            if result.get("ok") is False:
                last_error = str(result.get("error") or result.get("error_message") or "script failed")
                continue

            results = result.get("results", {})
            pdf_bytes = _extract_pdf_bytes_from_results(results)
            # нативный PDF из скрипта — тоже только fallback (и COM и OData)
            if pdf_bytes:
                native_pdf_fallback = native_pdf_fallback or pdf_bytes
                logger.info(
                    "Nova: native PDF from %s for %s (%s bytes) — keep as fallback, prefer portal",
                    script_key,
                    invoice_id,
                    len(pdf_bytes),
                )

            header, lines = _invoice_by_id_sections(results)
            org = _org_from_results(results)
            invoice_payload = self._enrich_com_pdf_payload(
                invoice_id,
                header,
                lines,
                org=org,
                tenant=tenant,
                script_results=results,
            )
            if invoice_payload:
                # хватает шапки+строк — дальше портальный PDF
                if _pdf_payload_has_supplier_banks(invoice_payload) or script_key == "invoice_by_id":
                    break
                if script_key == "invoice_pdf":
                    break

        if not invoice_payload:
            batch_header, batch_lines = self._lookup_batch_invoice(invoice_id)
            if batch_header:
                logger.info(
                    "Nova PDF: batch index for %s (invoice_by_id / invoice_pdf empty)",
                    invoice_id,
                )
                invoice_payload = self._enrich_com_pdf_payload(
                    invoice_id,
                    batch_header,
                    batch_lines,
                    org={},
                    tenant=tenant,
                    script_results=None,
                )

        # Кэшируем состав счёта независимо от того, найдутся ли ниже
        # реквизиты поставщика для рендера — сам факт "1С отдала номер/
        # строки/сумму" не должен теряться из-за отдельной проблемы с
        # ИИК/БИК в админке (см. invoice_pdf_cache.is_valid_pdf_payload —
        # банки больше не часть гейта валидности). Тихо: неудача кэширования
        # не должна ронять сам ответ пользователю с готовым PDF.
        if invoice_payload and tenant is not None:
            from app.db.database import SessionLocal
            from app.services.invoice_pdf_cache import store_payload_if_valid

            cache_db = SessionLocal()
            try:
                store_payload_if_valid(
                    cache_db, tenant.id, invoice_id, dict(invoice_payload), source="nova", tenant=tenant
                )
            except Exception:
                logger.debug("Nova: invoice_pdf_cache store failed for %s", invoice_id, exc_info=True)
            finally:
                cache_db.close()

        payload_has_banks = bool(invoice_payload) and _pdf_payload_has_supplier_banks(invoice_payload)

        # портальный макет (поставщик, таблица, печать/подпись из админки) — основной путь,
        # но только если реквизиты реально есть — иначе получаем "счёт" с пустым банком.
        if invoice_payload and payload_has_banks:
            try:
                from app.services.invoice_report import generate_formal_invoice_document

                generated = generate_formal_invoice_document(invoice_payload, str(out), tenant)
                if generated and Path(generated).is_file():
                    _write_pdf_cache_meta(Path(generated), invoice_payload)
                    logger.info(
                        "Nova: PDF счёта %s сформирован порталом (%s bytes, odata=%s)",
                        invoice_id,
                        Path(generated).stat().st_size,
                        bool(self._odata_org),
                    )
                    return str(Path(generated).resolve())
            except Exception as exc:
                last_error = f"Не удалось сформировать PDF из данных 1С: {exc}"
                logger.warning("Nova PDF render failed for %s: %s", invoice_id, exc)

        if native_pdf_fallback:
            logger.warning(
                "Nova: portal PDF не собрался/пропущен для %s — отдаём native fallback (%s bytes)",
                invoice_id,
                len(native_pdf_fallback),
            )
            return _write_pdf_bytes(native_pdf_fallback, "native fallback")

        if invoice_payload and not payload_has_banks:
            tenant_label = (
                getattr(tenant, "legal_name", None) or getattr(tenant, "name", None) or f"tenant_id={self._organization_id}"
            )
            raise MissingSupplierRequisitesError(
                f"У «{tenant_label}» не заполнены банковские реквизиты поставщика (ИИК/БИК/банк) — "
                "ни в 1С, ни в резервных полях. Заполните ИИК/БИК/Банк бенефициара в карточке "
                "арендатора в админке (раздел «Реквизиты счёта»), чтобы сформировать PDF счёта."
            )

        raise Nova1CServiceError(
            last_error
            or "Не удалось получить PDF счёта из 1С (onec.buh.getpdf / Nova script). "
            "Проверьте NOVA_MCP_RELAY_* и агент организации."
        )

    @staticmethod
    def _invoice_belongs_to_period(
        invoice_date_str: Optional[str],
        due_date_str: Optional[str],
        period: Optional[str],
    ) -> bool:
        if not period or len(period) != 7 or period[4] != "-":
            return True
        if not invoice_date_str and not due_date_str:
            return False
        try:
            period_year, period_month = int(period[:4]), int(period[5:7])
        except ValueError:
            return True

        for date_str in (invoice_date_str, due_date_str):
            if not date_str:
                continue
            raw = str(date_str).split("T")[0]
            if raw.startswith(period):
                return True
            inv_date = _parse_date_value(raw)
            if not inv_date:
                continue
            if inv_date.year == period_year and inv_date.month == period_month:
                return True
            prev_month = period_month - 1
            prev_year = period_year
            if prev_month < 1:
                prev_month = 12
                prev_year -= 1
            if inv_date.year == prev_year and inv_date.month == prev_month:
                return True
        return False

    @staticmethod
    def _period_invoice_fetch_bounds(period: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not period or len(period) != 7 or period[4] != "-":
            return None, None
        try:
            year = int(period[:4])
            month = int(period[5:7])
            if month < 1 or month > 12:
                return None, None
        except ValueError:
            return None, None
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        since = f"{prev_year}-{prev_month:02d}-01"
        until = f"{year}-{month:02d}-{monthrange(year, month)[1]}"
        return since, until

    @staticmethod
    def _payment_until_with_grace(until: Optional[str], grace_days: int = 45) -> Optional[str]:
        if not until:
            return None
        raw = str(until).split("T")[0]
        try:
            end = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return until
        return (end + timedelta(days=grace_days)).isoformat()

    def get_latest_invoice_status_by_counterparty(
        self,
        due_day: int = 5,
        period: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
    ) -> dict[str, dict]:
        since, until = self._period_invoice_fetch_bounds(period)
        payment_until = self._payment_until_with_grace(until)
        util_day = utilities_due_day if utilities_due_day is not None else due_day
        ops_day = operations_due_day if operations_due_day is not None else due_day
        invoices = self.get_invoices(
            since=since,
            until=until,
            limit=50000,
            due_day=due_day,
            enrich_payment_status=True,
            payment_since=since,
            payment_until=payment_until,
            utilities_due_day=util_day,
            operations_due_day=ops_day,
            period=period,
        )
        latest: dict[str, Invoice] = {}
        for inv in invoices:
            cp_key = (inv.counterparty_id or "").strip().lower()
            if not cp_key:
                continue
            if period and not self._invoice_belongs_to_period(inv.date, inv.due_date, period):
                continue
            prev = latest.get(cp_key)
            if not prev or (inv.date or "") > (prev.date or ""):
                latest[cp_key] = inv

        result: dict[str, dict] = {}
        for cp_key, inv in latest.items():
            doc_status = (
                "posted"
                if str(inv.status).lower() in ("posted", "true", "проведен")
                else "draft"
            )
            pay_status = str(inv.payment_status or "unpaid").lower()
            result[cp_key] = {
                "invoiceId": inv.id,
                "invoiceNumber": inv.number,
                "invoiceDate": inv.date or inv.due_date or "",
                "dueDate": inv.due_date,
                "documentStatus": doc_status,
                "paymentStatus": pay_status,
                "paidAt": inv.paid_at,
                "amount": inv.amount,
                "paidAmount": inv.paid_amount,
            }
        return result

    def upsert_counterparty_phone(
        self,
        counterparty_id: str,
        phone: str,
        *,
        kind_vid: Optional[str] = None,
    ) -> dict:
        """
        Запись телефона в 1С через Nova MCP OData (onec.buh.contacts_set).

        Только для OData-орг (City Mall). COM (Maxi) — skip.
        """
        self._ensure_agent_id()
        if not self._odata_org:
            logger.debug("Nova/COM: upsert_counterparty_phone skipped (not OData org)")
            return {
                "ok": False,
                "action": "skip",
                "message": "Запись телефона в 1С через Nova/COM не поддерживается",
            }
        if not relay_configured() or not self._agent_id:
            return {
                "ok": False,
                "action": "error",
                "message": "Nova MCP relay / agent_id не настроен для записи телефона",
            }

        from app.services.odata_1c_client import (
            _contact_phone_display,
            _extract_guid_key,
            _normalize_phone,
        )

        cp_id = _extract_guid_key(counterparty_id)
        display = _contact_phone_display(phone) or _normalize_phone(phone) or (phone or "").strip()
        if not cp_id or not display:
            return {
                "ok": False,
                "action": "error",
                "message": "Некорректный контрагент или телефон",
            }
        vid = (kind_vid or "").strip() or self.CONTACT_KIND_MOBILE
        try:
            item = call_buh_contacts_set(
                agent_id=self._agent_id,
                object_id=cp_id,
                value=display,
                vid=vid,
            )
        except NovaMcpRelayError as exc:
            logger.warning(
                "Nova OData contacts_set fail org=%s cp=%s: %s",
                self._organization_id,
                cp_id,
                exc,
            )
            return {"ok": False, "action": "error", "message": str(exc)}

        action = str(item.get("action") or "update").strip() or "update"
        if item.get("ok"):
            logger.info(
                "Nova OData phone %s org=%s cp=%s",
                action,
                self._organization_id,
                cp_id,
            )
            return {"ok": True, "action": action, "message": item.get("message") or ""}
        return {
            "ok": False,
            "action": action or "error",
            "message": item.get("message") or "1С отклонила сохранение телефона",
        }
