"""Real incident 2026-09-02: manual per-row sends worked fine on Maxi
Mall's slow/unreliable Nova org while the bulk debtor mailing hung/timed
out repeatedly. Root cause: queue_debtor_notifications ALWAYS called live
1C (invoice_service_types_from_1c) for every single invoice's service
type, even though sync_from_1c already computes and stores the exact same
classification on TenantPayment.service_type — the manual per-row path
never needed that live call (the type is already known/shown in the UI),
the bulk path paid for it 230+ times per run regardless.

Fix: trust payment.service_type first (parse_stored_service_types); only
fall back to the live 1C call when it's genuinely empty (legacy row, not
yet synced) — this test asserts the live call is skipped entirely once a
type is already stored, using the same test harness as
test_bulk_debtor_notify_service_type_filter.py."""
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
    trc = TRC(id=1, name="Maxi Mall")
    db_session.add(trc)
    t = Tenant(
        id=1,
        trc_id=1,
        name="Maxi Mall",
        legal_name="Maxi Mall LLP",
        one_c_login="",
        one_c_password="",
        nova_organization_id=119,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _make_invoice(db_session, tenant, *, service_type):
    payment = TenantPayment(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="Фармаком ТОО",
        invoice_date=date(2026, 9, 5),
        due_date=date(2026, 9, 15),
        status=PaymentStatus.UNPAID,
        period="2026-09",
        invoice_id="INV-1",
        counterparty_id="CP-1",
        service_type=service_type,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


@pytest.fixture(autouse=True)
def mocked_collaborators():
    fake_integration = SimpleNamespace(client=object(), close=lambda: None)
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
        "app.services.bulk_debtor_notify_service.reserve_send_slot",
        return_value=True,
    ), patch(
        "app.services.bulk_debtor_notify_service.NotificationService"
    ) as mock_notification_service_cls, patch(
        "app.services.whatsapp_jobs.process_whatsapp_job"
    ):
        # No PaymentService mock needed anymore — queue_debtor_notifications
        # sends straight off the TenantPayment row it already queried, it no
        # longer round-trips through
        # payment_service.ensure_payment_for_counterparty (see incident
        # 2026-09-03 fix in bulk_debtor_notify_service.py).
        mock_live_lookup.return_value = ["rent", "utilities"]
        mock_notification_service_cls.return_value.send_notification.return_value = (
            fake_notification,
            False,
        )
        yield mock_live_lookup


class TestTrustsStoredServiceType:
    def test_live_1c_lookup_never_called_when_service_type_already_stored(
        self, db_session, tenant, mocked_collaborators
    ):
        _make_invoice(db_session, tenant, service_type="rent")

        result = queue_debtor_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        mocked_collaborators.assert_not_called()
        assert result["queued"] == 1

    def test_multi_type_stored_field_still_sends_each_type(
        self, db_session, tenant, mocked_collaborators
    ):
        _make_invoice(db_session, tenant, service_type="rent,utilities")

        result = queue_debtor_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        mocked_collaborators.assert_not_called()
        assert result["queued"] == 2

    def test_falls_back_to_live_lookup_when_stored_field_is_empty(
        self, db_session, tenant, mocked_collaborators
    ):
        """Backward compatibility: a legacy row with no stored
        classification yet must still work exactly as before."""
        _make_invoice(db_session, tenant, service_type=None)

        result = queue_debtor_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        mocked_collaborators.assert_called_once()
        assert result["queued"] == 2

    def test_falls_back_to_live_lookup_when_stored_field_is_unknown(
        self, db_session, tenant, mocked_collaborators
    ):
        _make_invoice(db_session, tenant, service_type="unknown")

        result = queue_debtor_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        mocked_collaborators.assert_called_once()
        assert result["queued"] == 2
