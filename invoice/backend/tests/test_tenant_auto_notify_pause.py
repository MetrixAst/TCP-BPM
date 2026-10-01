"""PATCH /api/catalog/tenant/auto-notify — «Отключить авто-напоминания для
всех» кнопка в invoice-client (CounterpartiesTable). Distinct from the
per-counterparty pause (CounterpartyPhone.auto_notify_paused, see
test_counterparty_auto_notify_pause.py) — this one stops
AutoNotificationService.run_for_tenant for the whole tenant."""

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


def test_pause_and_resume_tenant_wide(client, db_session):
    trc, tenant = make_trc_tenant(db_session)
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.patch(
        "/api/catalog/tenant/auto-notify",
        json={"paused": True},
        params={"tenant_id": tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"auto_notify_paused": True}

    db_session.refresh(tenant)
    assert tenant.auto_notify_paused is True

    response = client.patch(
        "/api/catalog/tenant/auto-notify",
        json={"paused": False},
        params={"tenant_id": tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"auto_notify_paused": False}


def test_pause_requires_auth(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    response = client.patch(
        "/api/catalog/tenant/auto-notify",
        json={"paused": True},
        params={"tenant_id": tenant.id},
    )
    assert response.status_code == 401


def test_tenant_cannot_pause_another_tenant(client, db_session):
    trc, tenant = make_trc_tenant(db_session)
    other_tenant = Tenant(
        trc_id=trc.id,
        name="Other Tenant",
        legal_name="Other Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(other_tenant)
    db_session.commit()
    db_session.refresh(other_tenant)

    token = create_tenant_portal_token(tenant.id, trc.id)
    response = client.patch(
        "/api/catalog/tenant/auto-notify",
        json={"paused": True},
        params={"tenant_id": other_tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
