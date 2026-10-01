"""Сквозная проверка локального стенда (docker-compose.invoice.yml).

Создаёт ТЦ и арендатора в xlsx-режиме, загружает синтетический файл
Maxi Mall, назначает телефон, отправляет счета и проверяет, что заглушка
Green API получила PDF. Боевые 1С/Nova/WhatsApp не затрагиваются.

    python invoice/dev/smoke.py
"""
import os
import sys
import time
import uuid
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
from tests.xlsx_import.maxi_mall_fixture import build_workbook_bytes  # noqa: E402

API = os.getenv("INVOICE_API", "http://localhost:8004")
MOCK = os.getenv("GREENAPI_MOCK", "http://localhost:8099")
PERIOD = "2026-07"


def env_local(key):
    for line in (BACKEND / ".env.local").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise SystemExit(f"{key} нет в invoice/backend/.env.local")


def check(resp):
    if resp.status_code not in (200, 201):
        raise SystemExit(f"{resp.request.method} {resp.url} -> {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def step(msg):
    print(f"• {msg}")


def main():
    s = requests.Session()
    suffix = uuid.uuid4().hex[:6]

    token = check(s.post(f"{API}/api/admin/auth/login", json={
        "username": env_local("SUPER_ADMIN_USERNAME"),
        "password": env_local("SUPER_ADMIN_PASSWORD"),
    }))["access_token"]
    s.headers["Authorization"] = f"Bearer {token}"
    step("вход супер-админа")

    trc = check(s.post(f"{API}/api/admin/trcs", json={"name": f"Smoke TRC {suffix}"}))
    tenant = check(s.post(f"{API}/api/admin/trcs/{trc['id']}/tenants", json={
        "name": f"Smoke Tenant {suffix}",
        "legal_name": f"ТОО Smoke {suffix}",
        "org_type": "TOO",
        "bin_value": "123456789012",
        "xlsx_priority": "prefer_xlsx",
        "xlsx_parser_key": "maxi_mall",
        "green_api_url": "http://greenapi_mock:8080",
        "green_api_media_url": "http://greenapi_mock:8080",
        "green_api_id_instance": "1100000000",
        "green_api_api_token": "local-mock-token",
        "invoice_iik": "KZ000000000000000001",
        "invoice_kbe": "17",
        "invoice_bank_name": "АО Тестовый банк",
        "invoice_bank_bik": "TESTKZKA",
        "invoice_supplier_address": "г. Астана, ул. Тестовая, 1",
        "portal_username": f"smoke_{suffix}",
        "portal_password": "smoke-portal-pass",
    }))
    tid = tenant["id"]
    step(f"создан ТЦ #{trc['id']} и арендатор #{tid}")

    summary = check(s.post(
        f"{API}/api/xlsx-import/upload", params={"tenant_id": tid},
        files={"file": ("maxi_mall.xlsx", build_workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ))
    step(f"xlsx загружен: {summary}")

    payments = check(s.get(f"{API}/api/payments", params={"tenant_id": tid, "period": PERIOD}))
    items = payments["items"] if isinstance(payments, dict) else payments
    unpaid = [p for p in items if p.get("status") != "paid" and float(p.get("amount") or 0) > 0]
    step(f"платежей за {PERIOD}: {len(items)}, неоплаченных: {len(unpaid)}")
    if not unpaid:
        raise SystemExit("нет неоплаченных счетов для проверки отправки")

    cp_ids = sorted({p["counterparty_id"] for p in unpaid})
    for i, cp in enumerate(cp_ids):
        check(s.post(f"{API}/api/catalog/counterparty-phones", params={"tenant_id": tid},
                     json={"one_c_counterparty_id": cp, "phone": f"+7700000{i:04d}"}))
    step(f"телефоны назначены {len(cp_ids)} контрагентам")

    preview = check(s.get(f"{API}/api/notifications/send-xlsx-invoices/preview",
                          params={"tenant_id": tid, "period": PERIOD}))
    step(f"предпросмотр: {preview['message']}")
    if not preview["would_queue"]:
        raise SystemExit(f"нечего отправлять: {preview['skipped_rows']}")

    before = len(check(s.get(f"{MOCK}/_requests")))
    sent = check(s.post(f"{API}/api/notifications/send-xlsx-invoices",
                        params={"tenant_id": tid}, json={"period": PERIOD}))
    step(f"отправка: {sent}")

    files = []
    for _ in range(60):
        reqs = check(s.get(f"{MOCK}/_requests"))[before:]
        files = [r for r in reqs if r["method"] == "sendFileByUpload"]
        if len(files) >= preview["would_queue"]:
            break
        time.sleep(1)
    step(f"заглушка Green API получила файлов: {len(files)} (ожидалось {preview['would_queue']})")
    if len(files) < preview["would_queue"]:
        raise SystemExit("не все счета дошли до Green API")
    if not all("application/pdf" in r["body"] or "%PDF" in r["body"] for r in files):
        raise SystemExit("в запросах нет PDF")

    portal = requests.post(f"{API}/api/tenant-auth/login",
                           json={"username": f"smoke_{suffix}", "password": "smoke-portal-pass"})
    ptoken = check(portal)["access_token"]
    mine = check(requests.get(f"{API}/api/payments", params={"period": PERIOD},
                              headers={"Authorization": f"Bearer {ptoken}"}))
    mine_items = mine["items"] if isinstance(mine, dict) else mine
    step(f"кабинет арендатора: вход ок, видит платежей: {len(mine_items)}")
    if len(mine_items) != len(items):
        raise SystemExit("кабинет арендатора видит не те платежи")

    print("OK")


if __name__ == "__main__":
    main()
