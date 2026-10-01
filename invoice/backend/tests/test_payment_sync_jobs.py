"""run_payment_sync is the exact place a Moon-style silent failure (0 records,
status=done, nobody notified) would need to be caught. These tests pin down its
two outcomes: success writes the real record count via payment_sync_status.set_done,
failure writes the error via set_failed and still re-raises for the caller."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.catalog import Tenant
from app.models.payment_sync_run import PaymentSyncRun
from app.services import payment_sync_jobs, payment_sync_status

_SYNC_TEST_TABLES = [PaymentSyncRun.__table__, Tenant.__table__]


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=_SYNC_TEST_TABLES)
    return engine


@pytest.fixture()
def sync_session_factory(monkeypatch):
    engine = _make_engine()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(payment_sync_jobs, "SessionLocal", factory)
    return factory


def _add_tenant(factory, tenant_id: int, nova_organization_id=None):
    session = factory()
    session.add(
        Tenant(
            id=tenant_id,
            trc_id=1,
            name="Test Tenant",
            legal_name="Test Tenant LLP",
            one_c_login="",
            one_c_password="",
            nova_organization_id=nova_organization_id,
        )
    )
    session.commit()
    session.close()


def test_run_payment_sync_success_records_real_count(sync_session_factory):
    with patch("app.services.payment_sync_jobs.PaymentService") as MockService, patch(
        "app.services.payment_sync_jobs.invalidate_analytics_cache"
    ), patch("app.services.payment_sync_jobs.invalidate_invoice_status_cache"):
        MockService.return_value.sync_from_1c.return_value = [object(), object(), object()]

        count = payment_sync_jobs.run_payment_sync(4, "2025-01")

    assert count == 3
    session = sync_session_factory()
    status = payment_sync_status.get_status(session, 4, "2025-01")
    session.close()
    assert status["status"] == "done"
    assert status["records"] == 3
    assert status["error"] is None


def test_run_payment_sync_zero_records_is_still_status_done():
    """Documents the exact shape of the Moon incident: a sync that talks to the
    wrong backend "succeeds" with 0 records and status=done — nothing in this
    function's return value or DB row alone flags it as suspicious. See the two
    anomaly-log tests below for the actual signal."""
    engine = _make_engine()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with patch("app.services.payment_sync_jobs.SessionLocal", factory), patch(
        "app.services.payment_sync_jobs.PaymentService"
    ) as MockService, patch("app.services.payment_sync_jobs.invalidate_analytics_cache"), patch(
        "app.services.payment_sync_jobs.invalidate_invoice_status_cache"
    ):
        MockService.return_value.sync_from_1c.return_value = []

        count = payment_sync_jobs.run_payment_sync(4, "2026-08")

    assert count == 0
    session = factory()
    status = payment_sync_status.get_status(session, 4, "2026-08")
    session.close()
    assert status["status"] == "done"
    assert status["records"] == 0


def test_empty_sync_for_nova_tenant_logs_anomaly_warning(sync_session_factory):
    """The actual regression guard for the Moon incident: a tenant with
    nova_organization_id set getting 0 records must produce a greppable
    [SYNC-ANOMALY] log line — the hook a future alert (Sentry or otherwise)
    attaches to.

    Asserts on the logger call directly rather than via caplog: importing
    app.main (pulled in transitively through conftest's `from app.main import
    app`) runs `logging.basicConfig(force=True, ...)` as a *module-level* side
    effect (app/main.py:72, gated only by ENVIRONMENT != "production" — true
    for local/CI runs), which tears down whatever handler pytest's caplog
    fixture already attached to the root logger. Out of scope to fix here."""
    _add_tenant(sync_session_factory, tenant_id=4, nova_organization_id=127)

    with patch("app.services.payment_sync_jobs.PaymentService") as MockService, patch(
        "app.services.payment_sync_jobs.invalidate_analytics_cache"
    ), patch("app.services.payment_sync_jobs.invalidate_invoice_status_cache"), patch.object(
        payment_sync_jobs.logger, "warning"
    ) as mock_warning:
        MockService.return_value.sync_from_1c.return_value = []

        payment_sync_jobs.run_payment_sync(4, "2026-08")

    assert any(
        "[SYNC-ANOMALY]" in call.args[0] for call in mock_warning.call_args_list
    )


def test_empty_sync_for_non_nova_tenant_does_not_warn(sync_session_factory):
    """A tenant with no Nova org configured genuinely has no automated 1C source
    yet — 0 records there is expected, not an anomaly."""
    _add_tenant(sync_session_factory, tenant_id=5, nova_organization_id=None)

    with patch("app.services.payment_sync_jobs.PaymentService") as MockService, patch(
        "app.services.payment_sync_jobs.invalidate_analytics_cache"
    ), patch("app.services.payment_sync_jobs.invalidate_invoice_status_cache"), patch.object(
        payment_sync_jobs.logger, "warning"
    ) as mock_warning:
        MockService.return_value.sync_from_1c.return_value = []

        payment_sync_jobs.run_payment_sync(5, "2026-08")

    assert not any(
        "[SYNC-ANOMALY]" in call.args[0] for call in mock_warning.call_args_list
    )


def test_run_payment_sync_failure_records_error_and_reraises(sync_session_factory):
    with patch("app.services.payment_sync_jobs.PaymentService") as MockService, patch(
        "app.services.payment_sync_jobs.invalidate_analytics_cache"
    ), patch("app.services.payment_sync_jobs.invalidate_invoice_status_cache"):
        MockService.return_value.sync_from_1c.side_effect = RuntimeError("Nova недоступна")

        with pytest.raises(RuntimeError):
            payment_sync_jobs.run_payment_sync(4, "2025-01")

    session = sync_session_factory()
    status = payment_sync_status.get_status(session, 4, "2025-01")
    session.close()
    assert status["status"] == "failed"
    assert "Nova недоступна" in status["error"]
