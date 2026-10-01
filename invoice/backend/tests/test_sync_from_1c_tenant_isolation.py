"""PaymentService.sync_from_1c used to look up an "existing" row to
upsert purely by invoice_id, with no tenant scoping at all — COM/Nova
invoice ids aren't guaranteed globally unique across 1C organizations, so if
two different tenants' invoices ever collided on invoice_id, syncing tenant B
would find and silently overwrite tenant A's row (wrong amount, wrong
counterparty, tenant A's invoice vanishes from their own registry). See audit
from 2026-08-25, migration b0c1d2e3f4a5 (tenant_payments.tenant_id).

This pins down the fix: a colliding invoice_id must never touch another
tenant's row — sync_from_1c should create tenant B's own row instead.

Heavy collaborators that need a live 1C connection or a Postgres-only
CounterpartyCache table are stubbed out; only the upsert/scoping logic under
test runs for real against an in-memory DB.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _make_tenant(db_session, trc, **overrides) -> Tenant:
    defaults = dict(
        trc_id=trc.id,
        name="Tenant",
        legal_name="Tenant LLP",
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


def _service_for(db_session, tenant_id, fetch_payments_return):
    """PaymentService with 1C/cache collaborators stubbed so only the
    invoice-upsert scoping logic under test runs against the real DB."""
    service = PaymentService(db_session, tenant_id=tenant_id)
    service._load_counterparty_maps_for_sync = MagicMock(return_value=({}, {}, {}))
    service._backfill_payment_fields_from_1c_index = MagicMock(return_value=0)
    service._backfill_counterparty_ids_from_names = MagicMock(return_value=0)
    service.integration_1c.fetch_payments = MagicMock(return_value=fetch_payments_return)
    return service


def test_colliding_invoice_id_across_tenants_does_not_overwrite(db_session):
    trc = TRC(name="Test TRC")
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant_a = _make_tenant(db_session, trc, name="A", legal_name="Tenant A LLP")
    tenant_b = _make_tenant(db_session, trc, name="B", legal_name="Tenant B LLP")

    existing = TenantPayment(
        tenant_id=tenant_a.id,
        ip_name=tenant_a.legal_name,
        tenant_name="Original Counterparty",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 10),
        status=PaymentStatus.UNPAID,
        period="2026-08",
        invoice_id="INV-COLLIDE",
        amount=1000,
    )
    db_session.add(existing)
    db_session.commit()
    original_id = existing.id

    service_b = _service_for(
        db_session,
        tenant_b.id,
        [
            {
                "invoice_id": "INV-COLLIDE",
                "invoice_date": date(2026, 8, 2),
                "due_date": date(2026, 8, 12),
                "amount": 5000,
                "tenant_name": "Hijacked Counterparty",
                "counterparty_id": "cp-b",
            }
        ],
    )
    service_b.sync_from_1c("2026-08")

    # Tenant A's original row must be untouched.
    untouched = db_session.query(TenantPayment).filter(TenantPayment.id == original_id).one()
    assert untouched.tenant_id == tenant_a.id
    assert untouched.amount == 1000
    assert untouched.tenant_name == "Original Counterparty"
    assert untouched.ip_name == tenant_a.legal_name

    # Tenant B gets its own row for the same invoice_id instead of hijacking A's.
    rows = db_session.query(TenantPayment).filter(TenantPayment.invoice_id == "INV-COLLIDE").all()
    assert len(rows) == 2
    b_row = next(r for r in rows if r.id != original_id)
    assert b_row.tenant_id == tenant_b.id
    assert b_row.amount == 5000
    assert b_row.ip_name == tenant_b.legal_name


def test_same_tenant_resync_updates_its_own_row_in_place(db_session):
    """Sanity check the fix didn't break the normal (single-tenant) upsert
    path: re-syncing the same tenant/invoice should still update, not
    duplicate."""
    trc = TRC(name="Test TRC")
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = _make_tenant(db_session, trc, name="A", legal_name="Tenant A LLP")

    service = _service_for(
        db_session,
        tenant.id,
        [
            {
                "invoice_id": "INV-1",
                "invoice_date": date(2026, 8, 1),
                "due_date": date(2026, 8, 10),
                "amount": 1000,
                "tenant_name": "Counterparty",
                "counterparty_id": "cp-1",
            }
        ],
    )
    service.sync_from_1c("2026-08")

    service2 = _service_for(
        db_session,
        tenant.id,
        [
            {
                "invoice_id": "INV-1",
                "invoice_date": date(2026, 8, 1),
                "due_date": date(2026, 8, 10),
                "amount": 2000,
                "tenant_name": "Counterparty",
                "counterparty_id": "cp-1",
            }
        ],
    )
    service2.sync_from_1c("2026-08")

    rows = db_session.query(TenantPayment).filter(TenantPayment.invoice_id == "INV-1").all()
    assert len(rows) == 1
    assert rows[0].amount == 2000
    assert rows[0].tenant_id == tenant.id
