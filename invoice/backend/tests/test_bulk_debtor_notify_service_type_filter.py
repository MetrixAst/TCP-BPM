"""Regression coverage for the service-type filter added to the bulk debtor
mailing (queue_debtor_notifications' only_service_types param).

Before this change, the loop always sent one WhatsApp per service type found
on the invoice (rent/utilities/operations, resolved from 1C invoice lines).
The frontend now lets the operator restrict a bulk send to a single type
(e.g. only "Аренда"); this pins down that the backend actually honors that
restriction instead of silently sending every type anyway, and that the
"no filter" default keeps sending every type it finds (old behavior).

Heavy collaborators (1C client, WhatsApp send, payment/notification
persistence) are mocked out — this test is about the filtering decision
inside queue_debtor_notifications, not the full send pipeline.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.bulk_debtor_notify_service import queue_debtor_notifications

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
    trc = TRC(id=1, name="Test TRC")
    db_session.add(trc)
    t = Tenant(
        id=1,
        trc_id=1,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="odata.user",
        one_c_password="secret",
        nova_organization_id=118,
        # payment_{rent,utilities,operations}_enabled default to True on the model
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture()
def unpaid_invoice(db_session, tenant):
    payment = TenantPayment(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="ACME LLP",
        invoice_date=date(2026, 8, 5),
        due_date=date(2026, 8, 15),
        status=PaymentStatus.OVERDUE,
        period="2026-08",
        invoice_id="INV-1",
        counterparty_id="CP-1",
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


@pytest.fixture(autouse=True)
def mocked_collaborators(unpaid_invoice):
    """Stub every collaborator that would otherwise need a real 1C connection,
    a real WhatsApp send, or extra tables (CounterpartyPhone/Notification)
    this test doesn't need. Only the service-type filtering logic itself runs
    for real."""
    fake_integration = SimpleNamespace(client=object(), close=lambda: None)
    fake_notification = SimpleNamespace(id=99, payment_id=unpaid_invoice.id)

    with patch(
        "app.services.bulk_debtor_notify_service.get_integration_for_tenant",
        return_value=fake_integration,
    ), patch(
        "app.services.bulk_debtor_notify_service.get_trc_id_for_tenant",
        return_value=None,
    ), patch(
        "app.services.bulk_debtor_notify_service.invoice_service_types_from_1c",
        return_value=["rent", "utilities"],
    ), patch(
        "app.services.bulk_debtor_notify_service._resolve_auto_notify_phone",
        return_value="+77001234567",
    ), patch(
        "app.services.bulk_debtor_notify_service.reserve_send_slot",
        return_value=True,
    ), patch(
        "app.services.bulk_debtor_notify_service.NotificationService"
    ) as mock_notification_service_cls, patch(
        "app.services.whatsapp_jobs.process_whatsapp_job"
    ):
        # No PaymentService mock needed anymore — queue_debtor_notifications
        # sends straight off the TenantPayment row it already queried
        # (unpaid_invoice), it no longer round-trips through
        # payment_service.ensure_payment_for_counterparty (see incident
        # 2026-09-03 fix in bulk_debtor_notify_service.py).
        mock_notification_service_cls.return_value.send_notification.return_value = (
            fake_notification,
            False,
        )
        yield


def test_no_filter_sends_every_service_type_found_on_the_invoice(db_session, tenant):
    """Baseline / regression: with only_service_types omitted, behavior must be
    unchanged from before this feature — one message per type 1C reports."""
    result = queue_debtor_notifications(
        db_session, tenant_id=tenant.id, period="2026-08"
    )
    assert result["queued"] == 2  # rent + utilities
    assert result["skipped_service_type_filtered"] == 0


def test_filter_restricts_to_the_requested_type(db_session, tenant):
    result = queue_debtor_notifications(
        db_session,
        tenant_id=tenant.id,
        period="2026-08",
        only_service_types=["rent"],
    )
    assert result["queued"] == 1  # only rent, utilities dropped by the filter
    assert result["skipped_service_type_filtered"] == 0


def test_filter_skips_invoice_with_no_matching_type_and_counts_it(db_session, tenant):
    """Invoice only has rent/utilities lines; asking for operations-only must
    send nothing and say so via skipped_service_type_filtered — not silently
    fall through to skipped_no_service (that counter means something else:
    no service type resolved from 1C at all)."""
    result = queue_debtor_notifications(
        db_session,
        tenant_id=tenant.id,
        period="2026-08",
        only_service_types=["operations"],
    )
    assert result["queued"] == 0
    assert result["skipped_no_service"] == 0
    assert result["skipped_service_type_filtered"] == 1


def test_filter_is_case_and_whitespace_insensitive(db_session, tenant):
    """Defensive: frontend always sends lowercase keys, but the filter
    shouldn't silently drop everything if it ever received "Rent " or similar."""
    result = queue_debtor_notifications(
        db_session,
        tenant_id=tenant.id,
        period="2026-08",
        only_service_types=[" Rent "],
    )
    assert result["queued"] == 1


@pytest.fixture()
def other_counterparty_invoice(db_session, tenant):
    """A second debtor invoice for a different counterparty in the same
    period -- exists to prove the counterparty_id filter actually excludes
    it, not just that it doesn't crash with one row."""
    payment = TenantPayment(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="Other LLP",
        invoice_date=date(2026, 8, 6),
        due_date=date(2026, 8, 16),
        status=PaymentStatus.OVERDUE,
        period="2026-08",
        invoice_id="INV-2",
        counterparty_id="CP-2",
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


def test_counterparty_id_restricts_to_that_counterparty_only(
    db_session, tenant, other_counterparty_invoice
):
    """The «send all this counterparty's invoices» button on the counterparty
    card must not sweep up other debtors sharing the same period."""
    result = queue_debtor_notifications(
        db_session,
        tenant_id=tenant.id,
        period="2026-08",
        counterparty_id="CP-1",
    )
    assert result["queued"] == 2  # CP-1's rent + utilities only
    assert result["debtor_invoices"] == 1  # not CP-2's invoice


def test_counterparty_id_filter_is_case_insensitive(
    db_session, tenant, other_counterparty_invoice
):
    """1C GUIDs can come back in different letter casing depending on which
    method fetched them (see payment_service.py's own func.lower() lookups) —
    the filter must not silently match nothing because of that."""
    result = queue_debtor_notifications(
        db_session,
        tenant_id=tenant.id,
        period="2026-08",
        counterparty_id=" cp-1 ",
    )
    assert result["queued"] == 2
    assert result["debtor_invoices"] == 1


class TestCountDebtorCandidates:
    """count_debtor_candidates backs /send-debtors' fast synchronous response
    — it must never touch 1C (no mocked_collaborators needed) and must agree
    with queue_debtor_notifications' own filtering."""

    def test_counts_matching_rows_without_touching_1c(self, db_session, tenant, unpaid_invoice):
        from app.services.bulk_debtor_notify_service import count_debtor_candidates

        count = count_debtor_candidates(db_session, tenant_id=tenant.id, period="2026-08")
        assert count == 1

    def test_respects_counterparty_filter(
        self, db_session, tenant, unpaid_invoice, other_counterparty_invoice
    ):
        from app.services.bulk_debtor_notify_service import count_debtor_candidates

        assert count_debtor_candidates(
            db_session, tenant_id=tenant.id, period="2026-08", counterparty_id="CP-1"
        ) == 1
        assert count_debtor_candidates(
            db_session, tenant_id=tenant.id, period="2026-08"
        ) == 2

    def test_unknown_tenant_is_zero_not_an_error(self, db_session):
        from app.services.bulk_debtor_notify_service import count_debtor_candidates

        assert count_debtor_candidates(db_session, tenant_id=999999, period="2026-08") == 0


class TestRunDebtorNotificationsBackground:
    """/send-debtors no longer waits for the actual 1C-heavy pass (that's the
    504-on-large-batches bug) — it fires this in a FastAPI BackgroundTasks
    task instead. A background task must never raise: there's no request
    left to see the error, only logs."""

    def test_opens_its_own_db_session_not_the_request_scoped_one(self, db_session):
        import app.services.bulk_debtor_notify_service as svc

        with patch(
            "app.db.database.SessionLocal", return_value=db_session
        ) as session_factory, patch.object(
            svc, "queue_debtor_notifications", return_value={"queued": 1}
        ) as mock_queue:
            svc.run_debtor_notifications_background(
                tenant_id=1,
                period="2026-08",
                date_from=None,
                date_to=None,
                ignore_balance_filter=False,
                only_service_types=None,
                force=False,
                counterparty_id=None,
            )
            session_factory.assert_called_once()
            mock_queue.assert_called_once()
            assert mock_queue.call_args.kwargs["tenant_id"] == 1

    def test_does_not_raise_when_queue_notifications_fails(self, db_session):
        import app.services.bulk_debtor_notify_service as svc

        with patch("app.db.database.SessionLocal", return_value=db_session), patch.object(
            svc, "queue_debtor_notifications", side_effect=RuntimeError("1C down")
        ):
            svc.run_debtor_notifications_background(
                tenant_id=1,
                period="2026-08",
                date_from=None,
                date_to=None,
                ignore_balance_filter=False,
                only_service_types=None,
                force=False,
                counterparty_id=None,
            )  # must not raise
