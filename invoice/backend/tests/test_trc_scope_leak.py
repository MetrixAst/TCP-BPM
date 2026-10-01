"""Regression test for the cross-TRC data leak found 2026-08-26.

Before the fix, `resolve_tenant_id` returned `None` for a `trc`-role portal
login that didn't pass an explicit `tenant_id` query param. `None` means
"no tenant restriction" everywhere downstream (`PaymentService.
_apply_payment_filters`) — the same meaning it has for the admin JWT path,
which is intentional there but not for a TRC portal login. Since
invoice-client never sends `tenant_id`/`ip_name`/`tenant_name` for role
`trc` (by design — see `PaymentRegistry.tsx`), every TRC moderator saw
system-wide totals across every mall on login, not just their own.

This test reproduces exactly that: two TRCs, each with their own tenant and
payments, and asserts a fresh TRC login with zero payments of its own sees
zero — never the other TRC's data.
"""

from datetime import date
from unittest.mock import patch

import pytest

from app.core.security import create_trc_portal_token
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment

# _enrich_payment_tenant_names() unconditionally queries CounterpartyCache (a
# Postgres-only JSONB column, not renderable against this in-memory SQLite
# test DB — see test_get_payments_invoice_dedup.py's own comment on this).
# Every payment here already has tenant_name set, so the enrichment is a
# no-op either way; patch out the DB call it doesn't need rather than skip it.


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ):
        yield


def make_trc(db_session, **overrides) -> TRC:
    defaults = dict(name="Test TRC", is_active=True)
    defaults.update(overrides)
    trc = TRC(**defaults)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def make_tenant(db_session, trc: TRC, **overrides) -> Tenant:
    defaults = dict(
        trc_id=trc.id,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    defaults.update(overrides)
    tenant = Tenant(**defaults)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


_invoice_counter = [0]


def make_payment(db_session, tenant: Tenant, ip_name: str, **overrides) -> TenantPayment:
    _invoice_counter[0] += 1
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=f"INV-{_invoice_counter[0]}",
        ip_name=ip_name,
        tenant_name=ip_name,
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 10),
        status=PaymentStatus.UNPAID,
        period="2026-08",
        amount=100000,
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


def trc_headers(trc: TRC) -> dict:
    token = create_trc_portal_token(trc.id)
    return {"Authorization": f"Bearer {token}"}


def test_new_empty_trc_sees_no_payments_from_populated_trc(client, db_session):
    populated_trc = make_trc(db_session, name="Populated Mall")
    populated_tenant = make_tenant(db_session, populated_trc, legal_name="Populated LLP")
    for i in range(5):
        make_payment(db_session, populated_tenant, ip_name=f"Renter {i}")

    empty_trc = make_trc(db_session, name="Fresh Empty Mall")
    make_tenant(db_session, empty_trc, legal_name="Fresh LLP")

    response = client.get("/api/payments", headers=trc_headers(empty_trc))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_trc_without_explicit_tenant_id_sees_only_its_own_payments(client, db_session):
    trc_a = make_trc(db_session, name="Mall A")
    tenant_a = make_tenant(db_session, trc_a, legal_name="Tenant A LLP")
    make_payment(db_session, tenant_a, ip_name="Renter A")

    trc_b = make_trc(db_session, name="Mall B")
    tenant_b = make_tenant(db_session, trc_b, legal_name="Tenant B LLP")
    make_payment(db_session, tenant_b, ip_name="Renter B 1")
    make_payment(db_session, tenant_b, ip_name="Renter B 2")

    response_a = client.get("/api/payments", headers=trc_headers(trc_a))
    assert response_a.status_code == 200
    assert response_a.json()["total"] == 1

    response_b = client.get("/api/payments", headers=trc_headers(trc_b))
    assert response_b.status_code == 200
    assert response_b.json()["total"] == 2


def test_trc_with_multiple_tenants_requires_explicit_tenant_id(client, db_session):
    """Today every TRC has exactly one Tenant (auto-resolved, see tests
    above). If a TRC ever gets a second one, silently guessing which tenant
    to scope to would be as unsafe as the original bug — fail closed
    instead until the UI grows an explicit picker."""
    trc = make_trc(db_session, name="Multi-tenant Mall")
    make_tenant(db_session, trc, legal_name="Brand One LLP")
    make_tenant(db_session, trc, legal_name="Brand Two LLP")

    response = client.get("/api/payments", headers=trc_headers(trc))

    assert response.status_code == 400
