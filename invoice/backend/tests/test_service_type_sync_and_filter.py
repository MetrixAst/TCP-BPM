"""service_type persistence (sync_from_1c) and filtering (get_payments) for the
invoice-grained registry redesign — see discussion from 2026-08-25.

Reuses the stub-collaborator pattern from
tests/test_sync_from_1c_tenant_isolation.py: only the upsert/filter logic
under test runs against the real (in-memory) DB, 1C/cache calls are mocked.
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
from app.schemas.payment import PaymentFilter
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
    service = PaymentService(db_session, tenant_id=tenant_id)
    service._load_counterparty_maps_for_sync = MagicMock(return_value=({}, {}, {}))
    service._backfill_payment_fields_from_1c_index = MagicMock(return_value=0)
    service._backfill_counterparty_ids_from_names = MagicMock(return_value=0)
    service.integration_1c.fetch_payments = MagicMock(return_value=fetch_payments_return)
    return service


@pytest.fixture()
def trc(db_session):
    row = TRC(name="Test TRC")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class TestSyncPersistsServiceType:
    def test_new_row_gets_service_type_from_sync_item(self, db_session, trc):
        tenant = _make_tenant(db_session, trc)
        service = _service_for(
            db_session,
            tenant.id,
            [
                {
                    "invoice_id": "INV-1",
                    "invoice_date": date(2026, 8, 1),
                    "due_date": date(2026, 8, 10),
                    "amount": 125000,
                    "tenant_name": "Counterparty",
                    "counterparty_id": "cp-1",
                    "service_type": "signage",
                }
            ],
        )
        service.sync_from_1c("2026-08")

        row = db_session.query(TenantPayment).filter(TenantPayment.invoice_id == "INV-1").one()
        assert row.service_type == "signage"

    def test_resync_updates_service_type_if_it_changed(self, db_session, trc):
        """1C line items can be re-categorized between syncs (e.g. a line was
        added) — the stored value should track the latest classification."""
        tenant = _make_tenant(db_session, trc)
        service = _service_for(
            db_session,
            tenant.id,
            [
                {
                    "invoice_id": "INV-1",
                    "invoice_date": date(2026, 8, 1),
                    "due_date": date(2026, 8, 10),
                    "amount": 125000,
                    "tenant_name": "Counterparty",
                    "counterparty_id": "cp-1",
                    "service_type": "rent",
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
                    "amount": 125000,
                    "tenant_name": "Counterparty",
                    "counterparty_id": "cp-1",
                    "service_type": "rent,utilities",
                }
            ],
        )
        service2.sync_from_1c("2026-08")

        row = db_session.query(TenantPayment).filter(TenantPayment.invoice_id == "INV-1").one()
        assert row.service_type == "rent,utilities"


class TestGetPaymentsFilterByServiceType:
    def test_filters_to_matching_service_type(self, db_session, trc):
        tenant = _make_tenant(db_session, trc)
        db_session.add_all(
            [
                TenantPayment(
                    tenant_id=tenant.id,
                    ip_name=tenant.legal_name,
                    tenant_name="A",
                    invoice_date=date(2026, 8, 1),
                    due_date=date(2026, 8, 10),
                    status=PaymentStatus.UNPAID,
                    period="2026-08",
                    invoice_id="INV-RENT",
                    service_type="rent",
                ),
                TenantPayment(
                    tenant_id=tenant.id,
                    ip_name=tenant.legal_name,
                    tenant_name="B",
                    invoice_date=date(2026, 8, 1),
                    due_date=date(2026, 8, 10),
                    status=PaymentStatus.UNPAID,
                    period="2026-08",
                    invoice_id="INV-SIGNAGE",
                    service_type="signage",
                ),
            ]
        )
        db_session.commit()

        service = PaymentService(db_session, tenant_id=tenant.id)
        # CounterpartyCache uses a Postgres-only JSONB column, not available in
        # this in-memory SQLite test DB — the rows already have tenant_name set,
        # so this enrichment step is a no-op here; stub it out to avoid the
        # unrelated table-doesn't-exist error.
        service._counterparty_meta_index = MagicMock(return_value={})
        payments, total = service.get_payments(
            PaymentFilter(period="2026-08", service_type="signage", page=1, page_size=10)
        )
        assert [p.invoice_id for p in payments] == ["INV-SIGNAGE"]
        assert total == 1

    def test_matches_by_substring_for_multi_type_invoices(self, db_session, trc):
        tenant = _make_tenant(db_session, trc)
        db_session.add(
            TenantPayment(
                tenant_id=tenant.id,
                ip_name=tenant.legal_name,
                tenant_name="A",
                invoice_date=date(2026, 8, 1),
                due_date=date(2026, 8, 10),
                status=PaymentStatus.UNPAID,
                period="2026-08",
                invoice_id="INV-COMBO",
                service_type="rent,utilities",
            )
        )
        db_session.commit()

        service = PaymentService(db_session, tenant_id=tenant.id)
        service._counterparty_meta_index = MagicMock(return_value={})
        payments, total = service.get_payments(
            PaymentFilter(period="2026-08", service_type="utilities", page=1, page_size=10)
        )
        assert [p.invoice_id for p in payments] == ["INV-COMBO"]
        assert total == 1
