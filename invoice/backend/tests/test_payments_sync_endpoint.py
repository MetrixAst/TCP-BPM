from unittest.mock import patch

from app.core.security import create_tenant_portal_token
from app.models.catalog import TRC, Tenant


def make_trc_tenant(db_session):
    trc = TRC(name="Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def auth_headers(tenant, trc):
    token = create_tenant_portal_token(tenant.id, trc.id)
    return {"Authorization": f"Bearer {token}"}


def test_sync_endpoint_requires_auth(client, db_session):
    response = client.post("/api/payments/sync", params={"period": "2025-01"})
    assert response.status_code == 401


def test_sync_endpoint_starts_background_sync(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    with patch("app.api.payments._run_payment_sync_background") as mock_bg:
        response = client.post(
            "/api/payments/sync",
            params={"period": "2025-01"},
            headers=auth_headers(tenant, trc),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "started"
    assert body["period"] == "2025-01"
    mock_bg.assert_called_once_with(tenant.id, "2025-01", True)


def test_sync_endpoint_returns_running_when_already_in_progress(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    with patch("app.api.payments._run_payment_sync_background"):
        first = client.post(
            "/api/payments/sync",
            params={"period": "2025-01"},
            headers=auth_headers(tenant, trc),
        )
        assert first.json()["status"] == "started"

        second = client.post(
            "/api/payments/sync",
            params={"period": "2025-01"},
            headers=auth_headers(tenant, trc),
        )

    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "running"
