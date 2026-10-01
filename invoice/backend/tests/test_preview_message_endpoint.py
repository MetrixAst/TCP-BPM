"""GET /api/notifications/preview-message — requested 2026-09-02 right
after a real manual send to Maxi Mall turned out to have 3 real bugs at
once (wrong month, wrong period, falsely "overdue") that nobody could
have caught without actually sending. Lets an operator see the exact
built text before committing to a real send — zero side effects
(build_whatsapp_message only reads, never writes; no send-slot is
reserved, so a real send afterward sees the same candidates as if this
was never called)."""
from datetime import date

from app.core.security import create_access_token, hash_password
from app.models.catalog import TRC, AdminUser, Tenant
from app.models.notification import NotificationType
from app.models.payment import PaymentStatus, TenantPayment


def make_admin(db_session) -> AdminUser:
    admin = AdminUser(username="preview_test_admin", password_hash=hash_password("pw"), is_active=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def admin_headers(admin: AdminUser) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


def make_trc_tenant(db_session, **overrides) -> tuple[TRC, Tenant]:
    trc = TRC(name="Maxi Mall", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Maxi Mall",
        legal_name="Maxi Mall LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        **overrides,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def make_payment(db_session, tenant: Tenant, **overrides) -> TenantPayment:
    payment = TenantPayment(
        tenant_id=tenant.id,
        ip_name="Фармаком ТОО",
        tenant_name="Фармаком ТОО",
        invoice_date=date(2026, 9, 1),
        due_date=date(2026, 9, 15),
        status=PaymentStatus.UNPAID,
        period="2026-09",
        amount=116232,
        invoice_id="test-invoice-id",
        counterparty_id="cp-1",
        service_type="operations",
        source="one_c",
        **overrides,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


class TestPreviewMessageEndpoint:
    def test_returns_shifted_period_for_operations_when_tenant_flag_set(self, client, db_session):
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session, invoice_operations_advance_billing=True)
        payment = make_payment(db_session, tenant)

        resp = client.get(
            "/api/notifications/preview-message",
            params={
                "tenant_id": tenant.id,
                "payment_id": payment.id,
                "notification_type": NotificationType.WEEK_BEFORE.value,
                "service_type": "operations",
            },
            headers=admin_headers(admin),
        )
        assert resp.status_code == 200, resp.text
        message = resp.json()["message"]
        assert "Период: 2026-10" in message
        assert "Период: 2026-09" not in message

    def test_zero_side_effects_no_notification_or_log_row_created(self, client, db_session):
        from app.models.notification import Notification
        from app.models.auto_notification_log import AutoNotificationLog

        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session)
        payment = make_payment(db_session, tenant)

        client.get(
            "/api/notifications/preview-message",
            params={
                "tenant_id": tenant.id,
                "payment_id": payment.id,
                "notification_type": NotificationType.OVERDUE.value,
                "service_type": "operations",
            },
            headers=admin_headers(admin),
        )

        assert db_session.query(Notification).count() == 0
        assert db_session.query(AutoNotificationLog).count() == 0

    def test_missing_tenant_id_is_rejected(self, client, db_session):
        admin = make_admin(db_session)
        resp = client.get(
            "/api/notifications/preview-message",
            params={"notification_type": NotificationType.OVERDUE.value},
            headers=admin_headers(admin),
        )
        assert resp.status_code == 400
