"""GET /api/payments accepts service_type as a query param and filters by it —
part of the invoice-registry redesign (one row per invoice, filterable by
type), see discussion from 2026-08-25."""
from datetime import date
from unittest.mock import patch

import pytest

from app.core.security import create_tenant_portal_token
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment

# _enrich_payment_tenant_names() unconditionally queries CounterpartyCache
# (a Postgres-only JSONB column, not renderable against this in-memory SQLite
# test DB — see conftest.py's own comment on this). Every test payment here
# already has tenant_name set, so the enrichment is a no-op either way;
# patch out the DB call it doesn't need rather than skip it.


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ):
        yield


def make_trc_tenant(db_session):
    trc = TRC(name="Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def auth_headers(tenant, trc):
    token = create_tenant_portal_token(tenant.id, trc.id)
    return {"Authorization": f"Bearer {token}"}


def _add_payment(db_session, tenant, invoice_id, service_type):
    db_session.add(
        TenantPayment(
            tenant_id=tenant.id,
            ip_name=tenant.legal_name,
            tenant_name="ACME LLP",
            invoice_date=date(2026, 8, 1),
            due_date=date(2026, 8, 10),
            status=PaymentStatus.UNPAID,
            period="2026-08",
            invoice_id=invoice_id,
            service_type=service_type,
        )
    )
    db_session.commit()


def test_service_type_filter_returns_only_matching_invoices(client, db_session):
    trc, tenant = make_trc_tenant(db_session)
    _add_payment(db_session, tenant, "INV-RENT", "rent")
    _add_payment(db_session, tenant, "INV-SIGNAGE", "signage")
    _add_payment(db_session, tenant, "INV-ASSP", "assp")

    response = client.get(
        "/api/payments",
        params={"period": "2026-08", "service_type": "signage"},
        headers=auth_headers(tenant, trc),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["invoice_id"] for item in body["items"]] == ["INV-SIGNAGE"]
    assert body["total"] == 1


def test_no_service_type_filter_returns_all(client, db_session):
    trc, tenant = make_trc_tenant(db_session)
    _add_payment(db_session, tenant, "INV-RENT", "rent")
    _add_payment(db_session, tenant, "INV-SIGNAGE", "signage")

    response = client.get(
        "/api/payments",
        params={"period": "2026-08"},
        headers=auth_headers(tenant, trc),
    )

    assert response.status_code == 200
    body = response.json()
    assert {item["invoice_id"] for item in body["items"]} == {"INV-RENT", "INV-SIGNAGE"}


def test_payment_response_includes_service_type_field(client, db_session):
    trc, tenant = make_trc_tenant(db_session)
    _add_payment(db_session, tenant, "INV-COMBO", "rent,utilities")

    response = client.get(
        "/api/payments",
        params={"period": "2026-08"},
        headers=auth_headers(tenant, trc),
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["service_type"] == "rent,utilities"
