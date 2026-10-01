"""GET /api/admin/trcs/{trc_id}/counterparty-directory-xlsx — lets an admin
manually add phone numbers for counterparties that only exist via xlsx
import, without needing a live 1C connection at all.

counterparty_directory (the 1C-backed sibling) always 503s for a tenant
with no 1C credentials — its cache never gets populated by anything. This
is the parallel path: same response shape (reuses upsert_counterparty_phones
downstream), sourced from CounterpartyBalance(source="xlsx") instead."""
from app.core.security import create_access_token, hash_password
from app.models.catalog import TRC, Tenant, AdminUser, CounterpartyPhone
from app.models.counterparty_balance import CounterpartyBalance


def make_admin(db_session) -> AdminUser:
    admin = AdminUser(username="admin_test", password_hash=hash_password("pw"), is_active=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def admin_headers(admin: AdminUser) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


def make_trc_tenant(db_session) -> tuple[TRC, Tenant]:
    trc = TRC(name="Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id, name="Test Tenant", legal_name="Test Tenant LLP",
        one_c_login="", one_c_password="", is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def test_lists_xlsx_counterparties_without_1c(client, db_session):
    admin = make_admin(db_session)
    trc, tenant = make_trc_tenant(db_session)
    db_session.add(
        CounterpartyBalance(
            tenant_id=tenant.id, counterparty_id="virtual:abc123",
            counterparty_name="Unknown To 1C IP", debit=80000, credit=0, source="xlsx",
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/admin/trcs/{trc.id}/counterparty-directory-xlsx",
        params={"tenant_id": tenant.id},
        headers=admin_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["one_c_counterparty_id"] == "virtual:abc123"
    assert body[0]["counterparty_name"] == "Unknown To 1C IP"
    assert body[0]["bin_value"] is None
    assert body[0]["phone"] is None


def test_merges_already_saved_phone(client, db_session):
    admin = make_admin(db_session)
    trc, tenant = make_trc_tenant(db_session)
    db_session.add(
        CounterpartyBalance(
            tenant_id=tenant.id, counterparty_id="virtual:abc123",
            counterparty_name="Unknown To 1C IP", debit=80000, credit=0, source="xlsx",
        )
    )
    db_session.add(
        CounterpartyPhone(
            trc_id=trc.id, one_c_counterparty_id="virtual:abc123",
            counterparty_name="Unknown To 1C IP", phone="+77001234567",
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/admin/trcs/{trc.id}/counterparty-directory-xlsx",
        params={"tenant_id": tenant.id},
        headers=admin_headers(admin),
    )

    assert response.json()[0]["phone"] == "+77001234567"


def test_one_c_sourced_balance_rows_excluded(client, db_session):
    """Only source="xlsx" rows — a tenant with both 1C and xlsx data must
    not get its live 1C counterparties duplicated into this list too."""
    admin = make_admin(db_session)
    trc, tenant = make_trc_tenant(db_session)
    db_session.add(
        CounterpartyBalance(
            tenant_id=tenant.id, counterparty_id="1c-guid", counterparty_name="1C Renter",
            debit=1000, credit=0, source="one_c",
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/admin/trcs/{trc.id}/counterparty-directory-xlsx",
        params={"tenant_id": tenant.id},
        headers=admin_headers(admin),
    )

    assert response.json() == []


def test_unknown_tenant_404(client, db_session):
    admin = make_admin(db_session)
    trc, _tenant = make_trc_tenant(db_session)

    response = client.get(
        f"/api/admin/trcs/{trc.id}/counterparty-directory-xlsx",
        params={"tenant_id": 999999},
        headers=admin_headers(admin),
    )

    assert response.status_code == 404


def test_requires_admin_auth(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    response = client.get(
        f"/api/admin/trcs/{trc.id}/counterparty-directory-xlsx",
        params={"tenant_id": tenant.id},
    )

    assert response.status_code == 401
