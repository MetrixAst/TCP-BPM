"""POST /api/notifications/send-quick-message — quick WhatsApp templates
from the counterparty page (no invoice/PDF involved), requested
2026-09-18. Deliberately does NOT create a Notification row: payment_id
on that model is NOT NULL and there's no payment here — adding a
migration for 3-4 client-side-editable templates was explicitly ruled
out in favor of keeping this endpoint a thin pass-through to
WhatsAppService.send_message."""
from unittest.mock import MagicMock, patch

from app.core.security import create_access_token, hash_password
from app.models.catalog import TRC, AdminUser, Tenant
from app.models.notification import Notification


def make_admin(db_session) -> AdminUser:
    admin = AdminUser(username="quick_msg_test_admin", password_hash=hash_password("pw"), is_active=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def admin_headers(admin: AdminUser) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


def make_trc_tenant(db_session) -> tuple[TRC, Tenant]:
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
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


class TestSendQuickMessageEndpoint:
    def test_sends_plain_text_and_returns_success(self, client, db_session):
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session)

        fake_whatsapp = MagicMock()
        fake_whatsapp.send_message.return_value = True
        with patch(
            "app.services.tenant_whatsapp.get_whatsapp_for_tenant",
            return_value=fake_whatsapp,
        ):
            resp = client.post(
                "/api/notifications/send-quick-message",
                params={"tenant_id": tenant.id},
                json={
                    "counterparty_id": "cp-1",
                    "phone_number": "+77011234567",
                    "message": "Добрый день, Тестовый Арендатор!",
                },
                headers=admin_headers(admin),
            )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"success": True, "error": None}
        fake_whatsapp.send_message.assert_called_once_with(
            phone_number="+77011234567",
            message="Добрый день, Тестовый Арендатор!",
        )

    def test_does_not_create_a_notification_row(self, client, db_session):
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session)

        fake_whatsapp = MagicMock()
        fake_whatsapp.send_message.return_value = True
        with patch(
            "app.services.tenant_whatsapp.get_whatsapp_for_tenant",
            return_value=fake_whatsapp,
        ):
            client.post(
                "/api/notifications/send-quick-message",
                params={"tenant_id": tenant.id},
                json={
                    "counterparty_id": "cp-1",
                    "phone_number": "+77011234567",
                    "message": "Test",
                },
                headers=admin_headers(admin),
            )

        assert db_session.query(Notification).count() == 0

    def test_green_api_failure_returns_success_false_not_500(self, client, db_session):
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session)

        fake_whatsapp = MagicMock()
        fake_whatsapp.send_message.return_value = False
        with patch(
            "app.services.tenant_whatsapp.get_whatsapp_for_tenant",
            return_value=fake_whatsapp,
        ):
            resp = client.post(
                "/api/notifications/send-quick-message",
                params={"tenant_id": tenant.id},
                json={
                    "counterparty_id": "cp-1",
                    "phone_number": "+77011234567",
                    "message": "Test",
                },
                headers=admin_headers(admin),
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is False
        assert body["error"]

    def test_missing_tenant_id_is_rejected(self, client, db_session):
        admin = make_admin(db_session)
        resp = client.post(
            "/api/notifications/send-quick-message",
            json={
                "counterparty_id": "cp-1",
                "phone_number": "+77011234567",
                "message": "Test",
            },
            headers=admin_headers(admin),
        )
        assert resp.status_code == 400

    def test_empty_message_is_rejected(self, client, db_session):
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session)
        resp = client.post(
            "/api/notifications/send-quick-message",
            params={"tenant_id": tenant.id},
            json={"counterparty_id": "cp-1", "phone_number": "+77011234567", "message": ""},
            headers=admin_headers(admin),
        )
        assert resp.status_code == 422
