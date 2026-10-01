"""PaymentService.ensure_payment_for_counterparty used to require a live 1C
client unconditionally, even when the (counterparty_id, invoice_id) pair it
was asked for already had a matching TenantPayment row sitting in the DB —
the exact case its own "existing" lookup a few lines down would have found
for free. That meant any caller passing an already-known pair (bulk debtor
send, auto-reminders — see incident 2026-09-03 in
bulk_debtor_notify_service.py) got a hard 503 the moment 1C was flaky/down,
for a payment that didn't need 1C for anything.

Fix: look for the existing row first, using the raw counterparty_id/
invoice_id, before requiring integration.client. Only a genuinely new
payment (no local row yet) still needs — and correctly still requires — the
live 1C round-trip.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.db.database import Base
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.payment_service import PaymentService

_TEST_TABLES = [TRC.__table__, Tenant.__table__, TenantPayment.__table__]


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine, tables=_TEST_TABLES)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def tenant(db_session):
    trc = TRC(id=1, name="Fast Path TRC")
    db_session.add(trc)
    t = Tenant(
        id=1,
        trc_id=1,
        name="Fast Path Tenant",
        legal_name="Fast Path Tenant LLP",
        # Deliberately no 1C credentials/nova_organization_id at all — this
        # is what makes get_integration_for_tenant build an Integration1C
        # with client=None, same as a 1C-less / xlsx-only tenant, or one
        # whose credentials are temporarily broken.
        one_c_login="",
        one_c_password="",
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _make_payment(db_session, tenant) -> TenantPayment:
    payment = TenantPayment(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="ACME LLP",
        invoice_date=date(2026, 9, 5),
        due_date=date(2026, 9, 15),
        status=PaymentStatus.UNPAID,
        period="2026-09",
        invoice_id="INV-1",
        counterparty_id="CP-1",
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


class TestEnsurePaymentForCounterpartyFastPath:
    def test_returns_existing_row_without_requiring_1c_client(self, db_session, tenant):
        existing = _make_payment(db_session, tenant)
        svc = PaymentService(db_session, tenant_id=tenant.id)
        assert svc.integration_1c.client is None  # sanity: no 1C configured

        result = svc.ensure_payment_for_counterparty("CP-1", "INV-1")

        assert result.id == existing.id

    def test_case_and_whitespace_insensitive_lookup(self, db_session, tenant):
        existing = _make_payment(db_session, tenant)
        svc = PaymentService(db_session, tenant_id=tenant.id)

        result = svc.ensure_payment_for_counterparty(" cp-1 ", " INV-1 ")

        assert result.id == existing.id

    def test_still_requires_1c_client_for_a_genuinely_new_payment(self, db_session, tenant):
        """No local row for this pair — the function must still refuse to
        fabricate one out of thin air without 1C, same as before."""
        svc = PaymentService(db_session, tenant_id=tenant.id)

        with pytest.raises(HTTPException) as exc_info:
            svc.ensure_payment_for_counterparty("CP-2", "INV-NEW")

        assert exc_info.value.status_code == 503

    def test_does_not_leak_a_row_belonging_to_another_tenant(self, db_session, tenant):
        """tenant_id scoping must still apply on the fast path — a payment
        with the same invoice_id/counterparty_id under a different tenant
        must not be handed back (see 2026-08-25 audit referenced in
        payment_service.py)."""
        other_trc = TRC(id=2, name="Other TRC")
        db_session.add(other_trc)
        other_tenant = Tenant(
            id=2,
            trc_id=2,
            name="Other Tenant",
            legal_name="Other Tenant LLP",
            one_c_login="",
            one_c_password="",
        )
        db_session.add(other_tenant)
        db_session.commit()
        _make_payment(db_session, other_tenant)  # same INV-1/CP-1, tenant_id=2

        svc = PaymentService(db_session, tenant_id=tenant.id)  # tenant_id=1, no row here

        with pytest.raises(HTTPException) as exc_info:
            svc.ensure_payment_for_counterparty("CP-1", "INV-1")

        assert exc_info.value.status_code == 503
