from app.core.security import create_tenant_portal_token, create_trc_portal_token, hash_password
from app.models.catalog import TRC, Tenant


def make_trc(db_session, **overrides) -> TRC:
    defaults = dict(name="Test TRC", is_active=True)
    defaults.update(overrides)
    trc = TRC(**defaults)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def make_tenant(db_session, trc: TRC, **overrides) -> Tenant:
    defaults = dict(
        trc_id=trc.id,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    defaults.update(overrides)
    tenant = Tenant(**defaults)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def test_tenant_login_success(client, db_session):
    trc = make_trc(db_session)
    make_tenant(
        db_session,
        trc,
        portal_username="ipmoon_test",
        portal_password_hash=hash_password("moon_local_dev"),
    )

    response = client.post(
        "/api/tenant-auth/login",
        json={"username": "ipmoon_test", "password": "moon_local_dev"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "tenant"
    assert body["trc_id"] == trc.id
    assert body["access_token"]


def test_tenant_login_wrong_password(client, db_session):
    trc = make_trc(db_session)
    make_tenant(
        db_session,
        trc,
        portal_username="ipmoon_test",
        portal_password_hash=hash_password("moon_local_dev"),
    )

    response = client.post(
        "/api/tenant-auth/login",
        json={"username": "ipmoon_test", "password": "wrong"},
    )

    assert response.status_code == 401


def test_tenant_login_inactive_tenant_rejected(client, db_session):
    trc = make_trc(db_session)
    make_tenant(
        db_session,
        trc,
        portal_username="ipmoon_test",
        portal_password_hash=hash_password("moon_local_dev"),
        is_active=False,
    )

    response = client.post(
        "/api/tenant-auth/login",
        json={"username": "ipmoon_test", "password": "moon_local_dev"},
    )

    assert response.status_code == 401


def test_tenant_login_rejected_when_trc_inactive(client, db_session):
    trc = make_trc(db_session, is_active=False)
    make_tenant(
        db_session,
        trc,
        portal_username="ipmoon_test",
        portal_password_hash=hash_password("moon_local_dev"),
    )

    response = client.post(
        "/api/tenant-auth/login",
        json={"username": "ipmoon_test", "password": "moon_local_dev"},
    )

    assert response.status_code == 403


def test_trc_login_success(client, db_session):
    trc = make_trc(
        db_session,
        portal_username="citymall_ops",
        portal_password_hash=hash_password("ops_pw"),
    )

    response = client.post(
        "/api/tenant-auth/login",
        json={"username": "citymall_ops", "password": "ops_pw"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "trc"
    assert body["trc_id"] == trc.id
    assert body["tenant_id"] is None


def test_login_unknown_username_returns_401(client, db_session):
    response = client.post(
        "/api/tenant-auth/login",
        json={"username": "nobody", "password": "whatever"},
    )

    assert response.status_code == 401


def test_me_endpoint_returns_tenant_context(client, db_session):
    trc = make_trc(db_session)
    tenant = make_tenant(db_session, trc)
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.get(
        "/api/tenant-auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "tenant"
    assert body["tenant_id"] == tenant.id
    assert body["trc_id"] == trc.id


def test_me_endpoint_returns_trc_context(client, db_session):
    trc = make_trc(db_session)
    token = create_trc_portal_token(trc.id)

    response = client.get(
        "/api/tenant-auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "trc"
    assert body["tenant_id"] is None


def test_me_endpoint_without_token_rejected(client, db_session):
    response = client.get("/api/tenant-auth/me")

    assert response.status_code in (401, 403)


def test_me_xlsx_upload_available_false_by_default(client, db_session):
    """disabled priority (the actual DB default) — no upload button, even
    with a parser key set, per the "off for everyone by default" product
    decision (2026-08-26)."""
    trc = make_trc(db_session)
    tenant = make_tenant(db_session, trc, xlsx_parser_key="maxi_mall")
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.get("/api/tenant-auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["xlsx_upload_available"] is False


def test_me_xlsx_upload_available_requires_both_parser_and_priority(client, db_session):
    trc = make_trc(db_session)
    tenant = make_tenant(
        db_session, trc, xlsx_parser_key="maxi_mall", xlsx_priority="prefer_xlsx"
    )
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.get("/api/tenant-auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["xlsx_upload_available"] is True


def test_me_xlsx_upload_available_false_without_parser_even_if_priority_on(client, db_session):
    """Misconfiguration guard: admin flips priority on before a parser
    exists for this TC — upload must stay hidden rather than 422 on every
    attempt."""
    trc = make_trc(db_session)
    tenant = make_tenant(db_session, trc, xlsx_parser_key=None, xlsx_priority="prefer_xlsx")
    token = create_tenant_portal_token(tenant.id, trc.id)

    response = client.get("/api/tenant-auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["xlsx_upload_available"] is False


def test_me_xlsx_upload_available_true_for_trc_role(client, db_session):
    trc = make_trc(db_session)
    make_tenant(db_session, trc, xlsx_parser_key="maxi_mall", xlsx_priority="fallback_on_1c_failure")
    token = create_trc_portal_token(trc.id)

    response = client.get("/api/tenant-auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["xlsx_upload_available"] is True
