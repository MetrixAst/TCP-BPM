#!/usr/bin/env python3
"""Проверка реквизитов COM-PDF (ИИК, БИК, КНП, Кбе) для счёта.

Запуск в pod invoice-api (после деплоя backend):

    python backend/scripts/diagnose_com_pdf_requisites.py \\
        --org-id 119 \\
        --invoice-uid af5cfd7a-6f79-11f1-b51d-4c526260eadc

Ожидаемый результат: has_banks=True и заполнены supplier_iik, supplier_bik, payment_knp.
Если relay_configured=False — добавьте NOVA_MCP_RELAY_* в Secret pod'а.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.nova_buh_1c_client import (
    NovaBuh1CClient,
    _nova_uid_var,
    _org_from_results,
    _invoice_by_id_sections,
    _pdf_payload_has_supplier_banks,
    _resolve_downloads_path,
)
from app.services.nova_com_pdf_enrichment import (
    enrichment_from_script_results,
    fetch_com_pdf_enrichment,
)
from app.services.nova_mcp_relay import relay_configured


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", type=int, required=True)
    parser.add_argument("--invoice-uid", required=True)
    parser.add_argument("--generate-pdf", action="store_true", help="Собрать PDF в downloads/")
    args = parser.parse_args()

    print("=== ENV ===")
    print("relay_configured:", relay_configured())
    if not relay_configured():
        print(
            "WARN: NOVA_MCP_RELAY_URL / NOVA_MCP_RELAY_API_KEY не заданы — "
            "ИИК/БИК не подтянутся без MCP relay или шага banks в Nova-скрипте."
        )

    client = NovaBuh1CClient(organization_id=args.org_id)
    client._ensure_scripts()
    uid = _nova_uid_var(args.invoice_uid)
    print("agent_id:", client._agent_id)
    print("scripts:", client._script_ids)

    header, lines, org, results = None, [], {}, {}
    for key in ("invoice_pdf", "invoice_by_id"):
        if key not in client._script_ids:
            continue
        try:
            payload = client._run(key, vars={"uid": uid})
            results = (payload.get("result") or {}).get("results") or {}
            header, lines = _invoice_by_id_sections(results)
            org = _org_from_results(results)
            enrich = enrichment_from_script_results(results)
            print(f"\n=== Nova script: {key} ===")
            print("org:", {k: org.get(k) for k in (
                "supplier_name", "supplier_bin", "supplier_iik", "supplier_bik",
                "supplier_kbe", "payment_knp", "supplier_bank_name",
            )})
            if enrich:
                print("script enrich:", {k: enrich.get(k) for k in enrich if k != "line_units"})
            if isinstance(results.get("org"), dict):
                print("org columns:", results["org"].get("columns"))
            if results.get("banks"):
                print("banks step: present")
            else:
                print("banks step: MISSING (нужен deploy_nova_invoice_pdf.py --org-id", args.org_id, ")")
        except Exception as exc:
            print(f"=== {key} ERROR:", exc)

    if client._agent_id:
        relay = fetch_com_pdf_enrichment(
            agent_id=client._agent_id,
            invoice_uid=args.invoice_uid,
            uid_var=uid,
        )
        print("\n=== MCP relay enrichment ===")
        print(json.dumps(
            {k: relay.get(k) for k in (
                "supplier_bin", "supplier_iik", "supplier_bik", "supplier_kbe",
                "payment_knp", "supplier_bank_name",
            )},
            ensure_ascii=False,
            indent=2,
        ))

    pdf_payload = client._enrich_com_pdf_payload(
        args.invoice_uid,
        header,
        lines,
        org=org,
        tenant=None,
        script_results=results,
    )
    print("\n=== Итоговый payload для PDF ===")
    if not pdf_payload:
        print("FAIL: payload пустой")
        return 1
    for key in (
        "supplier_name", "supplier_bin", "supplier_iik", "supplier_bik",
        "supplier_kbe", "payment_knp", "supplier_bank_name",
    ):
        print(f"  {key}: {pdf_payload.get(key)!r}")
    has_banks = _pdf_payload_has_supplier_banks(pdf_payload)
    print("has_banks:", has_banks)

    if args.generate_pdf:
        out = _resolve_downloads_path(args.invoice_uid)
        if out.is_file():
            meta = out.with_suffix(".pdf.meta.json")
            out.unlink()
            meta.unlink(missing_ok=True)
            print("removed old cache:", out)
        path = client.download_invoice_file(args.invoice_uid, save_path=str(out))
        print("generated:", path, "size:", Path(path).stat().st_size if path else 0)

    return 0 if has_banks else 2


if __name__ == "__main__":
    raise SystemExit(main())
