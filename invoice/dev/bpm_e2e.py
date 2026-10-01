"""Сквозная проверка BPM -> сервис счетов -> заглушка Green API.

Нужен поднятый docker-compose.invoice.yml. Работает на отдельной SQLite-базе,
рабочую базу BPM не трогает:

    cd backend && POSTGRES_DB=/tmp/bpm_e2e.sqlite3 .venv/bin/python manage.py migrate
    POSTGRES_DB=/tmp/bpm_e2e.sqlite3 .venv/bin/python ../invoice/dev/bpm_e2e.py
"""
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
API = os.getenv("INVOICE_API", "http://localhost:8004")
MOCK = os.getenv("GREENAPI_MOCK", "http://localhost:8099")


def env_local(key):
    for line in (ROOT / "invoice/backend/.env.local").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise SystemExit(f"{key} нет в invoice/backend/.env.local")


def check(resp):
    if resp.status_code not in (200, 201):
        raise SystemExit(f"{resp.request.method} {resp.url} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def setup_service(cp_id, phone):
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + check(s.post(f"{API}/api/admin/auth/login", json={
        "username": env_local("SUPER_ADMIN_USERNAME"),
        "password": env_local("SUPER_ADMIN_PASSWORD"),
    }))["access_token"]
    suffix = uuid.uuid4().hex[:6]
    trc = check(s.post(f"{API}/api/admin/trcs", json={"name": f"BPM E2E TRC {suffix}"}))
    tenant = check(s.post(f"{API}/api/admin/trcs/{trc['id']}/tenants", json={
        "name": f"BPM E2E {suffix}",
        "legal_name": f"ТОО BPM E2E {suffix}",
        "org_type": "TOO",
        # 1С указана на закрытый порт: сервису нужен клиент 1С, но ходить в боевую нельзя.
        "one_c_login": "e2e",
        "one_c_password": "e2e",
        "one_c_base_url": "http://127.0.0.1:9",
        "green_api_url": "http://greenapi_mock:8080",
        "green_api_media_url": "http://greenapi_mock:8080",
        "green_api_id_instance": "1100000000",
        "green_api_api_token": "local-mock-token",
    }))
    check(s.post(f"{API}/api/catalog/counterparty-phones", params={"tenant_id": tenant["id"]},
                 json={"one_c_counterparty_id": cp_id, "phone": phone}))
    return tenant["id"]


def main():
    cp_id = f"bpm-e2e-{uuid.uuid4().hex[:8]}"
    phone = "+77015550101"
    tenant_id = setup_service(cp_id, phone)
    print(f"• в сервисе создана организация #{tenant_id}, телефон контрагента {cp_id} разрешён")

    os.environ.update(
        INVOICE_SERVICE_URL=API,
        INVOICE_SERVICE_USERNAME=env_local("SUPER_ADMIN_USERNAME"),
        INVOICE_SERVICE_PASSWORD=env_local("SUPER_ADMIN_PASSWORD"),
        INVOICE_SERVICE_TENANT_ID=str(tenant_id),
    )
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    import django

    django.setup()
    from django.core.cache import cache

    from finances.models import GeneratedInvoice, GeneratedInvoiceItem
    from finances.services import invoice_service
    from finances.services.notifications import send_invoice_via_whatsapp
    from onec.models import Counterparty

    cache.delete(invoice_service.TOKEN_CACHE_KEY)
    cp = Counterparty.objects.create(id_1c=cp_id, full_name="ТОО Ромашка", short_name="Ромашка", phone=phone)

    def make_invoice(number):
        inv = GeneratedInvoice.objects.create(number=number, total_amount=Decimal("150000"), counterparty=cp)
        GeneratedInvoiceItem.objects.create(
            invoice=inv, name="Аренда", quantity=1, price=Decimal("150000"), total=Decimal("150000"),
        )
        return inv

    before = len(check(requests.get(f"{MOCK}/_requests")))
    inv = make_invoice(f"E2E-{cp_id[-4:]}")
    ok, msg = send_invoice_via_whatsapp(inv)
    inv.refresh_from_db()
    print(f"• отправка счёта BPM: ok={ok}, «{msg}», статус={inv.status}, канал={inv.sent_via}")
    if not ok or inv.status != GeneratedInvoice.Status.SENT:
        raise SystemExit("счёт не отправлен")

    got = [r for r in check(requests.get(f"{MOCK}/_requests"))[before:] if r["method"] == "sendFileByUpload"]
    print(f"• заглушка Green API получила файлов: {len(got)}, размер {[r['size'] for r in got]}")
    if len(got) != 1 or "%PDF" not in got[0]["body"]:
        raise SystemExit("PDF счёта не дошёл до Green API")

    cp.phone = "+77019999999"
    cp.save()
    inv2 = make_invoice(f"E2E2-{cp_id[-4:]}")
    ok, msg = send_invoice_via_whatsapp(inv2)
    inv2.refresh_from_db()
    print(f"• чужой номер: ok={ok}, «{msg}», статус={inv2.status}")
    if ok or inv2.status != GeneratedInvoice.Status.CREATED or "не совпадает" not in msg:
        raise SystemExit("сервис должен отказать в отправке на чужой номер")

    print("OK")


if __name__ == "__main__":
    main()
