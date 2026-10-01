from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.security import create_access_token
from app.models.catalog import TRC, AdminUser, Tenant


def _admin_headers(db_session):
    db_session.add(AdminUser(username="send-file-admin", password_hash="x", is_active=True))
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(subject='send-file-admin')}"}


def _tenant(db_session):
    trc = TRC(name="Send File TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    tenant = Tenant(
        trc_id=trc.id, name="Send File Tenant", legal_name="Send File LLP",
        one_c_login="", one_c_password="", is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _post(client, headers, **form):
    return client.post(
        "/api/notifications/send-file",
        headers=headers,
        data={"phone_number": "+77001234567", **form},
        files={"file": ("invoice.pdf", b"%PDF-1.4 test", "application/pdf")},
    )


def test_requires_auth(client, db_session):
    tenant = _tenant(db_session)
    resp = _post(client, {}, tenant_id=str(tenant.id), counterparty_id="cp-1")
    assert resp.status_code == 401


def test_missing_counterparty_returns_400(client, db_session):
    headers = _admin_headers(db_session)
    tenant = _tenant(db_session)
    resp = _post(client, headers, tenant_id=str(tenant.id))
    assert resp.status_code == 400
    assert "counterparty_id" in resp.json()["detail"]


def test_unavailable_1c_returns_503(client, db_session):
    headers = _admin_headers(db_session)
    tenant = _tenant(db_session)
    with patch("app.api.notifications.get_integration_for_tenant",
               return_value=MagicMock(client=None)):
        resp = _post(client, headers, tenant_id=str(tenant.id), counterparty_id="cp-1")
    assert resp.status_code == 503


def test_foreign_phone_returns_403(client, db_session):
    headers = _admin_headers(db_session)
    tenant = _tenant(db_session)
    with patch("app.api.notifications.get_integration_for_tenant",
               return_value=MagicMock()), \
         patch("app.api.notifications.assert_phone_allowed_for_counterparty",
               side_effect=HTTPException(status_code=403, detail="Номер не совпадает")):
        resp = _post(client, headers, tenant_id=str(tenant.id), counterparty_id="cp-1")
    assert resp.status_code == 403


def test_success_delivers_file(client, db_session):
    headers = _admin_headers(db_session)
    tenant = _tenant(db_session)
    with patch("app.api.notifications.get_integration_for_tenant",
               return_value=MagicMock()), \
         patch("app.api.notifications.assert_phone_allowed_for_counterparty"), \
         patch("app.services.whatsapp_jobs.deliver_raw_message", return_value=True) as deliver:
        resp = _post(client, headers, tenant_id=str(tenant.id), counterparty_id="cp-1")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "message": "File sent successfully", "queued": False}
    assert deliver.call_args.kwargs["counterparty_id"] == "cp-1"
