"""PATCH /api/catalog/counterparty-phones/auto-notify — «Остановить авто-
напоминания» кнопка в invoice-client (CounterpartiesTable). Пауза хранится
на CounterpartyPhone.auto_notify_paused, см. auto_notification_service.py."""

from app.core.security import create_tenant_portal_token
from app.models.catalog import CounterpartyPhone, TRC, Tenant


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


def test_pause_creates_row_when_no_phone_saved(client, db_session):
    """Контрагент без сохранённого телефона (номер только из 1С) — паузу всё
    равно можно поставить, endpoint создаёт запись под флаг."""
    trc, tenant = make_trc_tenant(db_session)
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.patch(
        "/api/catalog/counterparty-phones/auto-notify",
        json={"one_c_counterparty_id": "CP-1", "paused": True},
        params={"tenant_id": tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["auto_notify_paused"] is True

    row = (
        db_session.query(CounterpartyPhone)
        .filter(CounterpartyPhone.trc_id == trc.id)
        .first()
    )
    assert row is not None
    assert row.auto_notify_paused is True
    assert row.phone == ""


def test_pause_toggle_preserves_existing_phone(client, db_session):
    """Ставим/снимаем паузу для контрагента, у которого уже сохранён телефон
    — сам номер и его роутинг не должны затираться."""
    trc, tenant = make_trc_tenant(db_session)
    token = create_tenant_portal_token(tenant.id, trc.id)
    row = CounterpartyPhone(
        trc_id=trc.id,
        one_c_counterparty_id="CP-2",
        phone="77001234567",
        phone_rent="77001234567",
    )
    db_session.add(row)
    db_session.commit()

    response = client.patch(
        "/api/catalog/counterparty-phones/auto-notify",
        json={"one_c_counterparty_id": "CP-2", "paused": True},
        params={"tenant_id": tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["auto_notify_paused"] is True
    assert body["phones"] == ["77001234567"]
    assert body["phone_rent"] == "77001234567"

    # снять паузу
    response = client.patch(
        "/api/catalog/counterparty-phones/auto-notify",
        json={"one_c_counterparty_id": "CP-2", "paused": False},
        params={"tenant_id": tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["auto_notify_paused"] is False


def test_get_counterparty_phones_reports_paused_default_false(client, db_session):
    trc, tenant = make_trc_tenant(db_session)
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.get(
        "/api/catalog/counterparty-phones",
        params={"counterparty_id": "CP-3", "tenant_id": tenant.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["auto_notify_paused"] is False


def test_pause_requires_auth(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    response = client.patch(
        "/api/catalog/counterparty-phones/auto-notify",
        json={"one_c_counterparty_id": "CP-4", "paused": True},
        params={"tenant_id": tenant.id},
    )
    assert response.status_code == 401
