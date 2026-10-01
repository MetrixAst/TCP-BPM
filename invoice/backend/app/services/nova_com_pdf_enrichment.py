"""Доп. данные из 1С COM для портального PDF (как OData _build_invoice_pdf_payload)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.nova_mcp_relay import NovaMcpRelayError, call_relay_tool, relay_configured
from app.services.nova_query_results import query_step_first_row, query_step_to_dicts

logger = logging.getLogger(__name__)

_META_QUERY = (
    "ВЫБРАТЬ "
    "Орг.НаименованиеПолное КАК supplier_name, "
    "Орг.ИдентификационныйНомер КАК supplier_bin, "
    "Орг.КБЕ КАК supplier_kbe, "
    "Счет.КодНазначенияПлатежа КАК payment_knp, "
    "ПРЕДСТАВЛЕНИЕ(Счет.ДоговорКонтрагента) КАК contract_text, "
    "К.ИдентификационныйКодЛичности КАК counterparty_bin, "
    "К.КБЕ КАК counterparty_kbe, "
    "К.НаименованиеПолное КАК counterparty_name_full "
    "ИЗ Документ.СчетНаОплатуПокупателю КАК Счет "
    "ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Организации КАК Орг ПО Счет.Организация = Орг.Ссылка "
    "ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Контрагенты КАК К ПО Счет.Контрагент = К.Ссылка "
    "ГДЕ Счет.Ссылка = &Ссылка"
)

_BANKS_QUERY = (
    "ВЫБРАТЬ "
    "БС.НомерСчета КАК supplier_iik, "
    "БС.Банк.БИК КАК supplier_bik, "
    "ПРЕДСТАВЛЕНИЕ(БС.Банк) КАК supplier_bank_name, "
    "ВЫБОР КОГДА БС.Ссылка = Орг.ОсновнойБанковскийСчет ТОГДА 0 ИНАЧЕ 1 КОНЕЦ КАК bank_rank "
    "ИЗ Документ.СчетНаОплатуПокупателю КАК Счет "
    "ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Организации КАК Орг ПО Счет.Организация = Орг.Ссылка "
    "ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.БанковскиеСчета КАК БС "
    "ПО БС.Владелец = Счет.Организация "
    "ГДЕ Счет.Ссылка = &Ссылка И НЕ БС.ПометкаУдаления"
)

_ADDRESSES_QUERY = (
    "ВЫБРАТЬ "
    "КИ.Представление КАК supplier_address, "
    "ПРЕДСТАВЛЕНИЕ(КИ.Вид) КАК kind "
    "ИЗ Документ.СчетНаОплатуПокупателю КАК Счет "
    "ВНУТРЕННЕЕ СОЕДИНЕНИЕ РегистрСведений.КонтактнаяИнформация КАК КИ "
    "ПО КИ.Объект = Счет.Организация "
    "ГДЕ Счет.Ссылка = &Ссылка "
    "И КИ.Тип = ЗНАЧЕНИЕ(Перечисление.ТипыКонтактнойИнформации.Адрес)"
)

_LINES_UNITS_QUERY = (
    "ВЫБРАТЬ "
    "ПРЕДСТАВЛЕНИЕ(Т.Номенклатура) КАК name, "
    "ПРЕДСТАВЛЕНИЕ(Т.Номенклатура.БазоваяЕдиницаИзмерения) КАК unit "
    "ИЗ Документ.СчетНаОплатуПокупателю.Услуги КАК Т "
    "ГДЕ Т.Ссылка = &Ссылка "
    "ОБЪЕДИНИТЬ ВСЕ "
    "ВЫБРАТЬ "
    "ПРЕДСТАВЛЕНИЕ(Т.Номенклатура), "
    "ПРЕДСТАВЛЕНИЕ(Т.Номенклатура.БазоваяЕдиницаИзмерения) "
    "ИЗ Документ.СчетНаОплатуПокупателю.Товары КАК Т "
    "ГДЕ Т.Ссылка = &Ссылка"
)


def _query_items(step_result: Any) -> list[dict]:
    return query_step_to_dicts(step_result)


def enrichment_from_script_results(results: dict) -> dict[str, Any]:
    """Реквизиты из шагов Nova-скрипта (org/banks/meta) без MCP relay."""
    if not isinstance(results, dict):
        return {}

    enrichment: dict[str, Any] = {}

    meta = query_step_first_row(results.get("meta"))
    if not meta:
        meta = query_step_first_row(results.get("org"))
    for key in (
        "supplier_name",
        "supplier_bin",
        "supplier_kbe",
        "payment_knp",
        "contract_text",
        "counterparty_bin",
        "counterparty_kbe",
        "counterparty_name_full",
        "supplier_iik",
        "supplier_bik",
        "supplier_bank_name",
        "supplier_address",
    ):
        val = meta.get(key)
        if val is not None and str(val).strip():
            enrichment[key] = str(val).strip()

    bank = _pick_supplier_bank(query_step_to_dicts(results.get("banks")))
    for key, val in bank.items():
        if val and not enrichment.get(key):
            enrichment[key] = val

    address = _pick_supplier_address(query_step_to_dicts(results.get("addresses")))
    if address and not enrichment.get("supplier_address"):
        enrichment["supplier_address"] = address

    units = _line_units_map(query_step_to_dicts(results.get("lines")))
    if units:
        enrichment["line_units"] = units
    return enrichment


def _pick_supplier_bank(rows: list[dict]) -> dict[str, str]:
    if not rows:
        return {}
    ranked = sorted(rows, key=lambda row: int(row.get("bank_rank") or 99))
    primary = ranked[0]
    if int(primary.get("bank_rank") or 1) == 0:
        return {
            "supplier_iik": str(primary.get("supplier_iik") or "").strip(),
            "supplier_bik": str(primary.get("supplier_bik") or "").strip(),
            "supplier_bank_name": str(primary.get("supplier_bank_name") or "").strip(),
        }
    filial = [
        row
        for row in ranked
        if "филиал" in str(row.get("supplier_bank_name") or "").lower()
    ]
    chosen = filial[0] if filial else ranked[0]
    return {
        "supplier_iik": str(chosen.get("supplier_iik") or "").strip(),
        "supplier_bik": str(chosen.get("supplier_bik") or "").strip(),
        "supplier_bank_name": str(chosen.get("supplier_bank_name") or "").strip(),
    }


def _pick_supplier_address(rows: list[dict]) -> str:
    for row in rows:
        kind = str(row.get("kind") or "").lower()
        if "юридич" in kind:
            return str(row.get("supplier_address") or "").strip()
    if rows:
        return str(rows[0].get("supplier_address") or "").strip()
    return ""


def _line_units_map(rows: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        unit = str(row.get("unit") or "").strip()
        if name and unit:
            out[name] = unit
    return out


def fetch_com_pdf_enrichment(
    *,
    agent_id: str,
    invoice_uid: str,
    uid_var: str,
) -> dict[str, Any]:
    """Один runScript: реквизиты org/cp, банки, адреса, единицы строк."""
    if not agent_id:
        return {}
    if not relay_configured():
        logger.warning(
            "COM PDF enrichment skipped for %s: NOVA_MCP_RELAY_URL / NOVA_MCP_RELAY_API_KEY "
            "не заданы (банки из Nova script org, контрагент — из кэша)",
            invoice_uid,
        )
        return {}

    arguments = {
        "vars": {"uid": uid_var},
        "steps": [
            {
                "id": "ref",
                "op": "com_call",
                "args": ["$uid"],
                "path": "Документы.СчетНаОплатуПокупателю",
                "method": "ПолучитьСсылку",
            },
            {
                "id": "meta",
                "op": "query",
                "text": _META_QUERY,
                "params": {"Ссылка": "$ref"},
            },
            {
                "id": "banks",
                "op": "query",
                "text": _BANKS_QUERY,
                "params": {"Ссылка": "$ref"},
            },
            {
                "id": "addresses",
                "op": "query",
                "text": _ADDRESSES_QUERY,
                "params": {"Ссылка": "$ref"},
            },
            {
                "id": "lines",
                "op": "query",
                "text": _LINES_UNITS_QUERY,
                "params": {"Ссылка": "$ref"},
            },
        ],
        "return": ["meta", "banks", "addresses", "lines"],
    }

    try:
        payload = call_relay_tool(
            agent_id=agent_id,
            tool="onec.com.runScript",
            arguments=arguments,
            timeout=120,
        )
    except NovaMcpRelayError as exc:
        logger.warning("COM PDF enrichment failed for %s: %s", invoice_uid, exc)
        return {}

    result = payload.get("result") or {}
    if result.get("ok") is False:
        logger.warning("COM PDF enrichment error for %s: %s", invoice_uid, result.get("error"))
        return {}

    results = result.get("results") or {}
    meta_rows = _query_items(results.get("meta"))
    bank_rows = _query_items(results.get("banks"))
    address_rows = _query_items(results.get("addresses"))
    line_rows = _query_items(results.get("lines"))

    meta = meta_rows[0] if meta_rows else {}
    bank = _pick_supplier_bank(bank_rows)
    address = _pick_supplier_address(address_rows)

    enrichment: dict[str, Any] = {}
    for key in (
        "supplier_name",
        "supplier_bin",
        "supplier_kbe",
        "payment_knp",
        "contract_text",
        "counterparty_bin",
        "counterparty_kbe",
        "counterparty_name_full",
    ):
        val = meta.get(key)
        if val is not None and str(val).strip():
            enrichment[key] = str(val).strip()
    enrichment.update(bank)
    if address:
        enrichment["supplier_address"] = address
    units = _line_units_map(line_rows)
    if units:
        enrichment["line_units"] = units
    return enrichment
