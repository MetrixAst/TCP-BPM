#!/usr/bin/env python3
"""Deploy/update Nova BUH script «PDF счёта по UID» for an organization."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.nova_com_pdf_enrichment import _BANKS_QUERY
from app.services.nova_1c_service import Nova1CServiceError, get_nova_1c_service

SCRIPT_NAME = "BUH: PDF счёта по UID"
SCRIPT_DESCRIPTION = "buh_invoice_pdf (COM via onec.com.runScript + print_form)"


ORG_REQUISITES_QUERY = (
    "ВЫБРАТЬ "
    "Счет.Организация.НаименованиеПолное КАК supplier_name, "
    "Счет.Организация.ИдентификационныйНомер КАК supplier_bin, "
    "Счет.Организация.КБЕ КАК supplier_kbe, "
    "Счет.Организация.ОсновнойБанковскийСчет.НомерСчета КАК supplier_iik, "
    "ПРЕДСТАВЛЕНИЕ(Счет.Организация.ОсновнойБанковскийСчет.Банк) КАК supplier_bank_name, "
    "Счет.Организация.ОсновнойБанковскийСчет.Банк.БИК КАК supplier_bik, "
    "Счет.КодНазначенияПлатежа КАК payment_knp, "
    "ПРЕДСТАВЛЕНИЕ(Счет.ДоговорКонтрагента) КАК contract_text "
    "ИЗ Документ.СчетНаОплатуПокупателю КАК Счет "
    "ГДЕ Счет.Ссылка = &Ссылка"
)


def _org_query_step() -> dict:
    return {
        "id": "org",
        "op": "query",
        "text": ORG_REQUISITES_QUERY,
        "params": {"Ссылка": "$ref"},
    }


def _banks_query_step() -> dict:
    return {
        "id": "banks",
        "op": "query",
        "text": _BANKS_QUERY,
        "params": {"Ссылка": "$ref"},
    }


def _build_pdf_script_body(invoice_by_id_body: dict, *, with_print_form: bool) -> dict:
    body = copy.deepcopy(invoice_by_id_body)
    body["_doc"] = (
        "PDF счёта на оплату по UID. Vars: uid — @uuid:... . "
        "Шаги: ссылка → org (реквизиты организации из 1С) → batch → print_form (нативный PDF). "
        "print_form требует патч COM-агента (backend/scripts/nova_agent_print_form.py). "
        "Без print_form портал строит PDF из batch+org."
    )
    steps = list(body.get("steps") or [])
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
    steps = [step for step in steps if step.get("id") not in {"obj", "pdf", "org", "banks"}]
    ref_idx = next((i for i, step in enumerate(steps) if step.get("id") == "ref"), -1)
    org_step = _org_query_step()
    banks_step = _banks_query_step()
    if ref_idx >= 0:
        steps.insert(ref_idx + 1, org_step)
        steps.insert(ref_idx + 2, banks_step)
    else:
        steps.insert(0, org_step)
        steps.insert(1, banks_step)
    if with_print_form:
        steps.append(
            {
                "id": "pdf",
                "op": "print_form",
                "ref": "$ref",
                "handler": "fsapi",
                "method": "СчетНаОплату",
                "layout": "СчетЗаказ",
                "format": "pdf",
            }
        )
    body["steps"] = steps
    body["vars"] = {"uid": "@uuid:00000000-0000-0000-0000-000000000001"}
    body["return"] = (
        ["batch", "org", "banks", "pdf"] if with_print_form else ["batch", "org", "banks"]
    )
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", type=int, required=True, help="Nova organization_id")
    parser.add_argument(
        "--source-script-id",
        type=int,
        default=20,
        help="Script ID to clone batch-query from (default: 20 «Счёт по UID»)",
    )
    parser.add_argument(
        "--no-print-form",
        action="store_true",
        help="Do not add print_form step (portal PDF fallback only; for agents without print_form op)",
    )
    args = parser.parse_args()

    svc = get_nova_1c_service()
    if not svc.configured():
        print("Nova API не настроен (NOVA_BACKEND_URL / NOVA_ADMIN_EMAIL / NOVA_ADMIN_PASSWORD)", file=sys.stderr)
        return 1

    source = svc._request(
        "GET",
        f"/api/v1/onec/scripts/{args.source_script_id}",
        params={"organization_id": args.org_id},
    )
    source_body = source.get("body") or {}
    if not source_body.get("steps"):
        print(f"Script {args.source_script_id} has no steps", file=sys.stderr)
        return 1

    body = _build_pdf_script_body(source_body, with_print_form=not args.no_print_form)
    saved = svc.upsert_script_by_name(
        args.org_id,
        name=SCRIPT_NAME,
        description=SCRIPT_DESCRIPTION,
        body=body,
    )
    print(json.dumps({"ok": True, "script_id": saved.get("ID"), "name": saved.get("name")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Nova1CServiceError as exc:
        print(f"Nova error: {exc}", file=sys.stderr)
        raise SystemExit(1)
