"""POST /admin/trcs/{trc_id}/green-api-pacing (+ per-tenant variant).

Обнаружено 2026-09-10 при проверке реального инстанса 720122720226 через
Green API getSettings: webhookUrl был пустым, outgoingAPIMessageWebhook="no" —
эндпоинт до этого умел настраивать только пейсинг, поэтому вебхук
outgoingMessageStatus не приходил вообще, и весь код на
whatsapp_jobs._process_green_api_webhook был мёртвым. Эти тесты — на HTTP-
уровне (conftest.client/db_session, полный набор таблиц), а не в
test_whatsapp_resilience.py, у которого свой урезанный db_session без
TRC/Tenant/AdminUser."""
from unittest.mock import patch

from app.core.security import create_access_token, hash_password
from app.models.catalog import TRC, AdminUser, Tenant
from app.services.whatsapp_service import WhatsAppService


def _make_trc(db_session, **overrides) -> TRC:
    defaults = dict(
        name="Pacing Test TRC",
        is_active=True,
        green_api_id_instance="720122720226",
        green_api_api_token="tok",
    )
    defaults.update(overrides)
    trc = TRC(**defaults)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def _super_admin_headers(db_session) -> dict:
    admin = AdminUser(
        username="super_admin_test",
        password_hash=hash_password("pw"),
        is_active=True,
        is_super=True,
    )
    db_session.add(admin)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


def _regular_admin_headers(db_session) -> dict:
    admin = AdminUser(
        username="regular_admin_test",
        password_hash=hash_password("pw"),
        is_active=True,
        is_super=False,
    )
    db_session.add(admin)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


class TestSetTrcGreenApiPacing:
    def test_super_admin_can_set_delay_and_webhook(self, client, db_session):
        trc = _make_trc(db_session)
        headers = _super_admin_headers(db_session)

        with patch.object(WhatsAppService, "set_send_delay", return_value=True) as set_mock:
            resp = client.post(
                f"/api/admin/trcs/{trc.id}/green-api-pacing",
                json={
                    "delay_ms": 45000,
                    "webhook_url": "https://api.invoice.metrix.com.ai/api/webhooks/green-api",
                },
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["id_instance"] == "720122720226"
        assert body["webhook_configured"] is True
        set_mock.assert_called_once_with(
            45000, "https://api.invoice.metrix.com.ai/api/webhooks/green-api"
        )

    def test_omitting_webhook_url_only_touches_pacing(self, client, db_session):
        trc = _make_trc(db_session)
        headers = _super_admin_headers(db_session)

        with patch.object(WhatsAppService, "set_send_delay", return_value=True):
            resp = client.post(
                f"/api/admin/trcs/{trc.id}/green-api-pacing",
                json={"delay_ms": 45000},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["webhook_configured"] is False

    def test_regular_admin_forbidden(self, client, db_session):
        trc = _make_trc(db_session)
        headers = _regular_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/green-api-pacing",
            json={"delay_ms": 45000},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_unknown_trc_404s(self, client, db_session):
        headers = _super_admin_headers(db_session)
        resp = client.post(
            "/api/admin/trcs/999999/green-api-pacing",
            json={"delay_ms": 45000},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_delay_out_of_range_rejected(self, client, db_session):
        trc = _make_trc(db_session)
        headers = _super_admin_headers(db_session)
        resp = client.post(
            f"/api/admin/trcs/{trc.id}/green-api-pacing",
            json={"delay_ms": 100},  # < 500мс, минимум Green API
            headers=headers,
        )
        assert resp.status_code == 422


class TestSetTenantGreenApiPacing:
    def test_tenant_level_webhook_configured_flag(self, client, db_session):
        trc = _make_trc(db_session)
        tenant = Tenant(
            trc_id=trc.id,
            name="Pacing Test Tenant",
            legal_name="Pacing Test Tenant LLP",
            one_c_login="",
            one_c_password="",
            green_api_id_instance="720122720226",
            green_api_api_token="tok",
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        headers = _super_admin_headers(db_session)

        with patch.object(WhatsAppService, "set_send_delay", return_value=True):
            resp = client.post(
                f"/api/admin/trcs/{trc.id}/tenants/{tenant.id}/green-api-pacing",
                json={
                    "delay_ms": 45000,
                    "webhook_url": "https://api.invoice.metrix.com.ai/api/webhooks/green-api",
                },
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["webhook_configured"] is True

    def test_tenant_not_in_trc_404s(self, client, db_session):
        trc = _make_trc(db_session)
        other_trc = _make_trc(db_session, name="Other TRC", green_api_id_instance="1")
        tenant = Tenant(
            trc_id=other_trc.id,
            name="Other Tenant",
            legal_name="Other Tenant LLP",
            one_c_login="",
            one_c_password="",
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        headers = _super_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/tenants/{tenant.id}/green-api-pacing",
            json={"delay_ms": 45000},
            headers=headers,
        )
        assert resp.status_code == 404
