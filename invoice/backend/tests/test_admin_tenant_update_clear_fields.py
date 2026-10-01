"""Real bug found 2026-09-02: PATCH /api/admin/trcs/{trc_id}/tenants/{tenant_id}
could never actually CLEAR an already-set optional field like
invoice_payment_knp — invoice-admin's form built the request body with
`field.trim() || undefined`, and `undefined` is dropped by JSON.stringify,
so the key was simply absent from the request. update_tenant's
`model_dump(exclude_unset=True)` then correctly (per its own semantics)
treats "key absent" as "leave unchanged", so the old value silently
persisted no matter how many times the admin cleared the field and saved.

The backend side of the fix is: it already worked correctly whenever the
key IS present with a null value (setattr(tenant, key, None) clears it
fine, since invoice_payment_knp and friends are ordinary nullable columns,
not in _PATCH_KEEP_IF_EMPTY). The actual bug was frontend-only (App.tsx
now sends `field.trim() || null` instead of `|| undefined`), but this
locks in the backend contract these tests rely on: explicit null in the
PATCH body must clear the field, and omitting the key must leave it
unchanged."""
from app.core.security import create_access_token, hash_password
from app.models.catalog import TRC, Tenant, AdminUser


def make_admin(db_session) -> AdminUser:
    admin = AdminUser(username="admin_clear_test", password_hash=hash_password("pw"), is_active=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def admin_headers(admin: AdminUser) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


def make_trc_tenant(db_session, **overrides) -> tuple[TRC, Tenant]:
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
        **overrides,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


class TestExplicitNullClearsOptionalFields:
    def test_explicit_null_clears_invoice_payment_knp(self, client, db_session):
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session, invoice_payment_knp="855")

        resp = client.patch(
            f"/api/admin/trcs/{trc.id}/tenants/{tenant.id}",
            json={"invoice_payment_knp": None},
            headers=admin_headers(admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["invoice_payment_knp"] is None

        db_session.refresh(tenant)
        assert tenant.invoice_payment_knp is None

    def test_omitted_field_leaves_invoice_payment_knp_unchanged(self, client, db_session):
        # The other half of the same contract: a field genuinely not sent
        # at all (this session's own "just rename the tenant" case) must
        # NOT be touched.
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session, invoice_payment_knp="855")

        resp = client.patch(
            f"/api/admin/trcs/{trc.id}/tenants/{tenant.id}",
            json={"name": "Renamed Tenant"},
            headers=admin_headers(admin),
        )
        assert resp.status_code == 200, resp.text

        db_session.refresh(tenant)
        assert tenant.invoice_payment_knp == "855"
        assert tenant.name == "Renamed Tenant"

    def test_explicit_null_clears_invoice_bank_bik(self, client, db_session):
        # Same contract, a second fallback field also hit by the same
        # frontend bug class (App.tsx's repeated `.trim() || undefined`).
        admin = make_admin(db_session)
        trc, tenant = make_trc_tenant(db_session, invoice_bank_bik="IRTYKZKA")

        resp = client.patch(
            f"/api/admin/trcs/{trc.id}/tenants/{tenant.id}",
            json={"invoice_bank_bik": None},
            headers=admin_headers(admin),
        )
        assert resp.status_code == 200, resp.text

        db_session.refresh(tenant)
        assert tenant.invoice_bank_bik is None
