"""
Reference patch for the Nova MCP Python COM adapter (onec.com.runScript).

Copy the functions below into the agent's script step dispatcher and extend
COM path whitelist. After deploy, redeploy the invoice PDF recipe:

    python backend/scripts/deploy_nova_invoice_pdf.py --org-id 119

Expected script step (see deploy_nova_invoice_pdf.py):

    {
        "id": "pdf",
        "op": "print_form",
        "ref": "$ref",
        "handler": "fsapi",
        "method": "СчетНаОплату",
        "layout": "СчетЗаказ",
        "format": "pdf"
    }

The step must put into script context / results:

    {"pdf_base64": "<base64>", "mime": "application/pdf", "filename": "invoice.pdf"}

Portal backend (nova_buh_1c_client._extract_pdf_bytes_from_results) already
consumes pdf_base64 from results.pdf or top-level keys.
"""

from __future__ import annotations

import base64
import os
import tempfile
from typing import Any, Callable, Mapping, Optional

# Extend the existing COM path whitelist in the agent, e.g.:
# ALLOWED_COM_ROOTS = ("Справочники", "Документы", "РегистрыСведений", "РегистрыНакопления", "Обработки")
ALLOWED_COM_ROOTS_WITH_PRINT = (
    "Справочники",
    "Документы",
    "РегистрыСведений",
    "РегистрыНакопления",
    "Обработки",
)

# 1C tabular document file type enum value for PDF (БСП / platform).
# Adjust if your platform build uses a different numeric constant.
TAB_DOC_FILE_PDF = 6


def resolve_ctx_ref(ctx: Mapping[str, Any], ref_expr: str) -> Any:
    """Resolve $ref / $uid style placeholders from script context."""
    raw = (ref_expr or "").strip()
    if raw.startswith("$"):
        key = raw[1:]
        if key not in ctx:
            raise KeyError(f"context key {raw!r} is missing")
        return ctx[key]
    return ref_expr


def _read_pdf_file(path: str) -> bytes:
    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"file is not a PDF: {path}")
    return data


def _export_tabular_doc_to_pdf(tab_doc: Any, out_path: str) -> bytes:
    """Write a 1C TabularDocument COM object to PDF on disk."""
    # tab_doc.Записать(Путь, ТипФайлаТабличногоДокумента.PDF)
    tab_doc.Записать(out_path, TAB_DOC_FILE_PDF)
    return _read_pdf_file(out_path)


def _print_via_fsapi(connection: Any, document_ref: Any, method: str) -> bytes:
    """
    Call external processing fsapi_ФормированиеДанных (used in BUH KZ recipes).

    The processing method usually returns a TabularDocument or a structure with
    a binary PDF field — try both shapes.
    """
    processing = connection.Обработки.fsapi_ФормированиеДанных.Создать()
    if not hasattr(processing, method):
        raise AttributeError(f"fsapi_ФормированиеДанных has no method {method!r}")
    result = getattr(processing, method)(document_ref)

    if result is None:
        raise ValueError(f"{method} returned empty result")

    # Tabular document
    if hasattr(result, "Записать"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        try:
            return _export_tabular_doc_to_pdf(result, tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # Structure / mapping with binary payload
    for attr in ("PDF", "Pdf", "Данные", "Файл", "ДвоичныеДанные", "Тело"):
        if hasattr(result, attr):
            raw = getattr(result, attr)
            if isinstance(raw, (bytes, bytearray)):
                data = bytes(raw)
                if data.startswith(b"%PDF"):
                    return data
            if isinstance(raw, str) and raw.strip():
                decoded = base64.b64decode(raw, validate=False)
                if decoded.startswith(b"%PDF"):
                    return decoded

    raise ValueError(f"{method} returned unsupported type: {type(result)!r}")


def _print_via_manage_print(
    connection: Any,
    document_ref: Any,
    *,
    layout: str,
) -> bytes:
    """
    Fallback: standard BSP print manager (УправлениеПечатью).
    layout example: 'СчетЗаказ' for invoice.
    """
    print_mgr = connection.Обработки.УправлениеПечатью.Создать()
    identifiers = connection.NewObject("Массив")
    identifiers.Add(document_ref)

    # СформироватьПечатныеФормы(ИмяМенеджера, Идентификаторы, ПараметрыПечати)
    manager_name = "Документ.СчетНаОплатуПокупателю"
    print_params = connection.NewObject("Структура")
    collection = print_mgr.СформироватьПечатныеФормы(
        manager_name,
        identifiers,
        print_params,
    )
    if collection is None:
        raise ValueError("УправлениеПечатью returned empty collection")

    # collection is usually a ValueTable: find row with matching layout name
    count = int(collection.Количество())
    for idx in range(count):
        row = collection.Get(idx)
        name = str(getattr(row, "ИмяМакета", "") or getattr(row, "Имя", "") or "")
        if layout and layout.lower() not in name.lower():
            continue
        tab_doc = getattr(row, "ТабличныйДокумент", None) or getattr(row, "Документ", None)
        if tab_doc is None:
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        try:
            return _export_tabular_doc_to_pdf(tab_doc, tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    raise ValueError(f"print layout {layout!r} not found in collection ({count} rows)")


def op_print_form(
    step: Mapping[str, Any],
    ctx: Mapping[str, Any],
    *,
    connection: Any,
) -> dict[str, Any]:
    """
    Execute print_form script step. Register in dispatcher:

        if op == "print_form":
            ctx[step_id] = op_print_form(step, ctx, connection=conn)
    """
    ref = resolve_ctx_ref(ctx, str(step.get("ref") or step.get("document_ref") or "$ref"))
    handler = (step.get("handler") or "fsapi").strip().lower()
    method = (step.get("method") or "СчетНаОплату").strip()
    layout = (step.get("layout") or "СчетЗаказ").strip()
    out_format = (step.get("format") or "pdf").strip().lower()
    if out_format != "pdf":
        raise ValueError(f"unsupported print format: {out_format!r}")

    if handler == "fsapi":
        try:
            pdf_bytes = _print_via_fsapi(connection, ref, method)
        except Exception as fsapi_exc:
            # Graceful fallback to BSP print manager when fsapi is missing.
            pdf_bytes = _print_via_manage_print(connection, ref, layout=layout)
            return {
                "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                "mime": "application/pdf",
                "filename": "invoice.pdf",
                "source": "manage_print",
                "fsapi_error": str(fsapi_exc),
            }
        return {
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "mime": "application/pdf",
            "filename": "invoice.pdf",
            "source": "fsapi",
        }

    if handler in ("manage_print", "bsp", "управлениепечатью"):
        pdf_bytes = _print_via_manage_print(connection, ref, layout=layout)
        return {
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "mime": "application/pdf",
            "filename": "invoice.pdf",
            "source": "manage_print",
        }

    raise ValueError(f"unknown print_form handler: {handler!r}")


def register_print_form_op(dispatch: dict[str, Callable[..., Any]]) -> None:
    """dispatch[op_name] = handler(step, ctx, connection=...)"""
    dispatch["print_form"] = op_print_form
