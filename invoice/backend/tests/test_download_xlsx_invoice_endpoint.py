"""GET /api/payments/xlsx/{invoice_id}/download — end-to-end HTTP tests for
the xlsx-invoice PDF path added 2026-08-31 (see app/services/xlsx_invoice_pdf.py
docstring for why this exists as a separate endpoint from
/1c/invoices/{invoice_id}/download).

find_counterparty_in_cache() and generate_formal_invoice_document() are
patched in every test: the former hits CounterpartyCache, a Postgres-only
JSONB table this in-memory SQLite test DB can't render (see conftest.py's
own note); the latter does real font/PDF rendering, irrelevant to what
these tests check (auth, ownership, status codes, response bytes)."""
from datetime import date
from unittest.mock import patch

import pytest

from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.core.security import (
    create_access_token,
    create_tenant_portal_token,
    create_trc_portal_token,
)
from app.models.catalog import TRC, AdminUser, Tenant
from app.models.payment import PaymentStatus, TenantPayment


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.xlsx_invoice_pdf.find_counterparty_in_cache",
        return_value=None,
    ):
        yield


def make_trc(db_session, **overrides) -> TRC:
    defaults = dict(name="Download Test TRC", is_active=True)
    defaults.update(overrides)
    trc = TRC(**defaults)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def make_tenant(db_session, trc: TRC, **overrides) -> Tenant:
    defaults = dict(
        trc_id=trc.id,
        name="Download Test Tenant",
        legal_name="Download Test Tenant LLP",
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


def make_xlsx_payment(db_session, tenant: Tenant, **overrides) -> TenantPayment:
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id="xlsx:1:2026-08:cp-1:rent",
        ip_name="Арендатор",
        tenant_name="Арендатор",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        status=PaymentStatus.UNPAID,
        period="2026-08",
        amount=150000,
        counterparty_id="cp-1",
        service_type="rent",
        source="xlsx",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


def _admin_headers(db_session) -> dict:
    admin = AdminUser(username="admin", password_hash="x", is_active=True)
    db_session.add(admin)
    db_session.commit()
    token = create_access_token(subject="admin")
    return {"Authorization": f"Bearer {token}"}


class TestDownloadXlsxInvoice:
    def test_no_auth_returns_401(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)

        resp = client.get(f"/api/payments/xlsx/{payment.invoice_id}/download")

        assert resp.status_code == 401

    def test_own_tenant_portal_login_downloads_pdf(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        pdf_path = tmp_path / "invoice.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake xlsx invoice")

        with patch(
            "app.api.payments.render_xlsx_invoice_pdf", return_value=str(pdf_path)
        ):
            resp = client.get(
                f"/api/payments/xlsx/{payment.invoice_id}/download",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == b"%PDF-1.4 fake xlsx invoice"

    def test_trc_portal_login_downloads_own_tenants_invoice(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        token = create_trc_portal_token(trc_id=trc.id)

        pdf_path = tmp_path / "invoice.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "app.api.payments.render_xlsx_invoice_pdf", return_value=str(pdf_path)
        ):
            resp = client.get(
                f"/api/payments/xlsx/{payment.invoice_id}/download",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200

    def test_other_tenant_portal_login_gets_403(self, client, db_session, tmp_path):
        trc1 = make_trc(db_session, name="TRC One")
        trc2 = make_trc(db_session, name="TRC Two")
        tenant1 = make_tenant(db_session, trc1, name="Tenant One", legal_name="Tenant One LLP")
        tenant2 = make_tenant(db_session, trc2, name="Tenant Two", legal_name="Tenant Two LLP")
        payment = make_xlsx_payment(db_session, tenant1)
        token = create_tenant_portal_token(tenant_id=tenant2.id, trc_id=trc2.id)

        resp = client.get(
            f"/api/payments/xlsx/{payment.invoice_id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    def test_other_trc_portal_login_gets_403(self, client, db_session):
        trc1 = make_trc(db_session, name="TRC One")
        trc2 = make_trc(db_session, name="TRC Two")
        tenant1 = make_tenant(db_session, trc1, name="Tenant One", legal_name="Tenant One LLP")
        make_tenant(db_session, trc2, name="Tenant Two", legal_name="Tenant Two LLP")
        payment = make_xlsx_payment(db_session, tenant1)
        token = create_trc_portal_token(trc_id=trc2.id)

        resp = client.get(
            f"/api/payments/xlsx/{payment.invoice_id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    def test_admin_can_download_any_tenants_invoice(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        headers = _admin_headers(db_session)

        pdf_path = tmp_path / "invoice.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "app.api.payments.render_xlsx_invoice_pdf", return_value=str(pdf_path)
        ):
            resp = client.get(
                f"/api/payments/xlsx/{payment.invoice_id}/download",
                headers=headers,
            )

        assert resp.status_code == 200

    def test_nonexistent_payment_returns_404(self, client, db_session):
        headers = _admin_headers(db_session)

        resp = client.get("/api/payments/xlsx/999999/download", headers=headers)

        assert resp.status_code == 404

    def test_one_c_sourced_payment_rejected_with_400(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant, source="one_c", invoice_id="real-1c-guid")
        headers = _admin_headers(db_session)

        resp = client.get(f"/api/payments/xlsx/{payment.invoice_id}/download", headers=headers)

        assert resp.status_code == 400

    def test_missing_amount_returns_422_not_a_blank_pdf(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant, amount=None)
        headers = _admin_headers(db_session)

        resp = client.get(f"/api/payments/xlsx/{payment.invoice_id}/download", headers=headers)

        assert resp.status_code == 422

    def test_missing_supplier_requisites_returns_422(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        headers = _admin_headers(db_session)

        with patch(
            "app.api.payments.render_xlsx_invoice_pdf",
            side_effect=MissingSupplierRequisitesError("нет IIK/BIK"),
        ):
            resp = client.get(f"/api/payments/xlsx/{payment.invoice_id}/download", headers=headers)

        assert resp.status_code == 422

    def test_render_failure_returns_500_not_a_broken_pdf(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        headers = _admin_headers(db_session)

        with patch("app.api.payments.render_xlsx_invoice_pdf", return_value=None):
            resp = client.get(f"/api/payments/xlsx/{payment.invoice_id}/download", headers=headers)

        assert resp.status_code == 500
