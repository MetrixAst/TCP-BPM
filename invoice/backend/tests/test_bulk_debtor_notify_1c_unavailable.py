"""Incident 2026-09-03: bulk debtor send silently sent nothing while manual
single send for the same counterparty/invoice kept working fine.

Root cause (two compounding bugs in queue_debtor_notifications):

1. It hard-required a live 1C client (`if not integration.client: return
   {...errors: 1}`) BEFORE doing anything else, aborting the entire run —
   even though nothing after that point actually needed 1C for a payment we
   already had locally: service-type classification already trusted
   `payment.service_type` first (see
   test_bulk_debtor_notify_trusts_stored_service_type.py), and phone
   resolution already falls back to admin-configured numbers. That abort
   result never reached the operator either: POST /send-debtors answers
   *before* this function runs at all (see app/api/notifications.py::
   send_debtors_bulk — count_debtor_candidates never touches 1C), so the
   operator saw "started, N debtors found" while zero messages were ever
   attempted.

2. Even with #1 fixed, every row went through
   payment_service.ensure_payment_for_counterparty(cp_id, invoice_id,
   integration=integration) — which itself unconditionally required
   integration.client before even checking whether the row already existed
   in the DB (it did: it's literally the row this loop is iterating over).

3. reserve_send_slot's bulk_<date> reservation was committed *before* the
   send was attempted and never released on failure (by design, for the
   Kafka-success case) — so a row that failed for reason #1/#2 stayed
   falsely marked "sent today" and a same-day retry silently skipped it as
   a duplicate unless the operator knew to pass force=True.

This file pins down the fix for all three: 1C being unavailable degrades
gracefully instead of aborting the whole run, and a row that fails before
being handed off to Kafka/the background thread releases its slot so an
immediate retry (no force needed) actually goes out.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.auto_notification_log import AutoNotificationLog
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.bulk_debtor_notify_service import queue_debtor_notifications

_TEST_TABLES = [
    TRC.__table__,
    Tenant.__table__,
    TenantPayment.__table__,
    AutoNotificationLog.__table__,
]


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
    trc = TRC(id=1, name="Nova Flaky Mall")
    db_session.add(trc)
    t = Tenant(
        id=1,
        trc_id=1,
        name="Nova Flaky Mall",
        legal_name="Nova Flaky Mall LLP",
        one_c_login="",
        one_c_password="",
        nova_organization_id=119,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _make_invoice(db_session, tenant, *, service_type="rent", invoice_id="INV-1"):
    payment = TenantPayment(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="Фармаком ТОО",
        invoice_date=date(2026, 9, 5),
        due_date=date(2026, 9, 15),
        status=PaymentStatus.UNPAID,
        period="2026-09",
        invoice_id=invoice_id,
        counterparty_id="CP-1",
        service_type=service_type,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


class TestBulkSurvives1CUnavailable:
    """Bulk debtor send must not go to zero just because the 1C connection
    used to construct this particular Integration1C happened to be down —
    manual single-send survives the same condition via its cached-PDF /
    payment-trusted fallbacks; bulk must too."""

    def test_queues_normally_when_1c_client_is_none_and_service_type_is_stored(
        self, db_session, tenant
    ):
        _make_invoice(db_session, tenant, service_type="rent")
        fake_integration = SimpleNamespace(
            client=None,
            close=lambda: None,
            unavailable_message=lambda: "1C недоступна (тест)",
        )
        fake_notification = SimpleNamespace(id=99, payment_id=1)

        with patch(
            "app.services.bulk_debtor_notify_service.get_integration_for_tenant",
            return_value=fake_integration,
        ), patch(
            "app.services.bulk_debtor_notify_service.get_trc_id_for_tenant",
            return_value=None,
        ), patch(
            "app.services.bulk_debtor_notify_service.invoice_service_types_from_1c"
        ) as mock_live_lookup, patch(
            "app.services.bulk_debtor_notify_service._resolve_auto_notify_phone",
            return_value="+77001234567",
        ), patch(
            "app.services.bulk_debtor_notify_service.NotificationService"
        ) as mock_notification_service_cls, patch(
            "app.services.whatsapp_jobs.process_whatsapp_job"
        ):
            mock_notification_service_cls.return_value.send_notification.return_value = (
                fake_notification,
                False,
            )

            result = queue_debtor_notifications(
                db_session, tenant_id=tenant.id, period="2026-09"
            )

            # Must not have needed the live classification call at all —
            # payment.service_type was already stored.
            mock_live_lookup.assert_not_called()

        assert result["errors"] == 0
        assert result["queued"] == 1
        assert result["skipped_no_service"] == 0

    def test_degrades_to_skipped_no_service_instead_of_aborting_whole_run(
        self, db_session, tenant
    ):
        """No stored service_type AND 1C down: this one invoice can't be
        classified (no live fallback available) — it must be counted via
        skipped_no_service, not blow up the entire tenant's run the way the
        old `if not integration.client: return {...errors: 1}` guard did."""
        _make_invoice(db_session, tenant, service_type=None)
        fake_integration = SimpleNamespace(
            client=None,
            close=lambda: None,
            unavailable_message=lambda: "1C недоступна (тест)",
        )

        with patch(
            "app.services.bulk_debtor_notify_service.get_integration_for_tenant",
            return_value=fake_integration,
        ), patch(
            "app.services.bulk_debtor_notify_service.get_trc_id_for_tenant",
            return_value=None,
        ), patch(
            "app.services.bulk_debtor_notify_service._resolve_auto_notify_phone",
            return_value="+77001234567",
        ), patch(
            "app.services.bulk_debtor_notify_service.NotificationService"
        ):
            result = queue_debtor_notifications(
                db_session, tenant_id=tenant.id, period="2026-09"
            )

        assert result["errors"] == 0
        assert result["queued"] == 0
        assert result["skipped_no_service"] == 1
        assert result["debtor_invoices"] == 1


class TestFailedRowReleasesItsSendSlot:
    """A row that fails before being handed off to Kafka/the background
    thread must release its bulk_<date> reservation, so a same-day retry
    (no force=True needed) can actually go out instead of being silently
    reported as skipped_duplicate."""

    def _run_with_send_failing_once(self, db_session, tenant):
        fake_integration = SimpleNamespace(client=object(), close=lambda: None)
        fake_notification = SimpleNamespace(id=99, payment_id=1)

        with patch(
            "app.services.bulk_debtor_notify_service.get_integration_for_tenant",
            return_value=fake_integration,
        ), patch(
            "app.services.bulk_debtor_notify_service.get_trc_id_for_tenant",
            return_value=None,
        ), patch(
            "app.services.bulk_debtor_notify_service._resolve_auto_notify_phone",
            return_value="+77001234567",
        ), patch(
            "app.services.bulk_debtor_notify_service.NotificationService"
        ) as mock_notification_service_cls, patch(
            "app.services.whatsapp_jobs.process_whatsapp_job"
        ):
            mock_notification_service_cls.return_value.send_notification.side_effect = (
                RuntimeError("1C timeout building payment snapshot")
            )
            first = queue_debtor_notifications(
                db_session, tenant_id=tenant.id, period="2026-09"
            )

            mock_notification_service_cls.return_value.send_notification.side_effect = None
            mock_notification_service_cls.return_value.send_notification.return_value = (
                fake_notification,
                False,
            )
            second = queue_debtor_notifications(
                db_session, tenant_id=tenant.id, period="2026-09"
            )
        return first, second

    def test_first_attempt_fails_second_attempt_same_day_still_sends_without_force(
        self, db_session, tenant
    ):
        _make_invoice(db_session, tenant, service_type="rent")

        first, second = self._run_with_send_failing_once(db_session, tenant)

        assert first["errors"] == 1
        assert first["queued"] == 0

        # No force=True passed — this only succeeds if the failed attempt's
        # reservation was actually released.
        assert second["errors"] == 0
        assert second["queued"] == 1
        assert second["skipped_duplicate"] == 0

    def test_failed_attempt_leaves_no_orphaned_reservation_row(
        self, db_session, tenant
    ):
        _make_invoice(db_session, tenant, service_type="rent")

        first, _second = self._run_with_send_failing_once(db_session, tenant)
        assert first["errors"] == 1

        # The second run in _run_with_send_failing_once already re-reserves
        # and succeeds; check there is exactly one row (from the successful
        # second attempt), not two/orphaned from the first.
        rows = db_session.query(AutoNotificationLog).all()
        assert len(rows) == 1
        assert rows[0].invoice_id == "INV-1"
        assert rows[0].service_type == "rent"
