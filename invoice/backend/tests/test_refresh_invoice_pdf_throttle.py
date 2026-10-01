"""POST /api/admin/invoices/{invoice_id}/refresh-pdf — force-refresh must be
rate-limited per (tenant_id, invoice_id), or it becomes a ready-made way to
reproduce the exact Nova 502-storm incident the payload cache exists to
prevent (see fix/whatsapp-pdf-retry-and-text-fallback, 2026-08-25/26, and
memory invoice_pdf_payload_cache_plan)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.security import create_access_token, hash_password
from app.models.catalog import TRC, AdminUser, Tenant
from app.models.invoice_pdf_payload import InvoicePdfPayload
from app.services.invoice_pdf_cache import FORCE_REFRESH_COOLDOWN

_INVOICE_ID = "f49e3940-9563-11f1-b522-4c526260eadb"


def make_super_admin(db_session) -> AdminUser:
    admin = AdminUser(username="super_admin_test", password_hash=hash_password("pw"), is_active=True, is_super=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def admin_headers(admin: AdminUser) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


def make_tenant(db_session) -> Tenant:
    trc = TRC(name="Throttle Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id, name="Throttle Test Tenant", legal_name="Throttle Test Tenant LLP",
        one_c_login="odata.user", one_c_password="secret", is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _fake_integration(pdf_path="downloads/invoice_fake.pdf") -> MagicMock:
    integration = MagicMock()
    integration.client.access_token = "already-authenticated"
    integration.download_invoice_file.return_value = pdf_path
    integration.close = MagicMock()
    return integration


class TestForceRefreshThrottle:
    def test_first_force_refresh_allowed(self, client, db_session, tmp_path):
        admin = make_super_admin(db_session)
        tenant = make_tenant(db_session)
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        with patch("app.services.tenant_1c.get_tenant_by_id", return_value=tenant), patch(
            "app.services.tenant_1c.get_integration_for_tenant",
            return_value=_fake_integration(str(pdf)),
        ):
            response = client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )

        assert response.status_code == 200
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _INVOICE_ID
        ).first()
        assert row is not None
        assert row.last_force_refresh_attempt_at is not None

    def test_immediate_second_force_refresh_is_throttled(self, client, db_session, tmp_path):
        admin = make_super_admin(db_session)
        tenant = make_tenant(db_session)
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        fake_integration = _fake_integration(str(pdf))

        with patch("app.services.tenant_1c.get_tenant_by_id", return_value=tenant), patch(
            "app.services.tenant_1c.get_integration_for_tenant", return_value=fake_integration
        ):
            first = client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )
            assert first.status_code == 200

            second = client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )

        assert second.status_code == 429
        # The second attempt must never even reach 1C.
        assert fake_integration.download_invoice_file.call_count == 1

    def test_throttled_regardless_of_whether_any_payload_ever_cached(self, client, db_session, tmp_path):
        """The gap found during design: an invoice that never produces a
        valid payload must still be throttleable on repeated force=True
        spam, not just ones that already have a real cache entry."""
        admin = make_super_admin(db_session)
        tenant = make_tenant(db_session)
        failing_integration = _fake_integration(pdf_path=None)
        failing_integration.download_invoice_file.return_value = None

        with patch("app.services.tenant_1c.get_tenant_by_id", return_value=tenant), patch(
            "app.services.tenant_1c.get_integration_for_tenant", return_value=failing_integration
        ):
            first = client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )
            assert first.status_code == 404  # "PDF не удалось сформировать"

            second = client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )

        assert second.status_code == 429
        assert failing_integration.download_invoice_file.call_count == 1

    def test_attempt_allowed_again_after_cooldown_elapses(self, client, db_session, tmp_path):
        admin = make_super_admin(db_session)
        tenant = make_tenant(db_session)
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        fake_integration = _fake_integration(str(pdf))

        with patch("app.services.tenant_1c.get_tenant_by_id", return_value=tenant), patch(
            "app.services.tenant_1c.get_integration_for_tenant", return_value=fake_integration
        ):
            client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )
            row = db_session.query(InvoicePdfPayload).filter(
                InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _INVOICE_ID
            ).first()
            row.last_force_refresh_attempt_at = (
                datetime.now(timezone.utc) - FORCE_REFRESH_COOLDOWN - timedelta(seconds=1)
            )
            db_session.commit()

            second = client.post(
                f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
                params={"tenant_id": tenant.id},
                headers=admin_headers(admin),
            )

        assert second.status_code == 200
        assert fake_integration.download_invoice_file.call_count == 2

    def test_non_super_admin_still_rejected_before_throttle_check(self, client, db_session):
        """admin.is_super gate must run first — a non-super admin gets 403,
        not a throttle-related response, and never touches the DB row."""
        admin = AdminUser(username="regular_admin", password_hash=hash_password("pw"), is_active=True, is_super=False)
        db_session.add(admin)
        db_session.commit()
        tenant = make_tenant(db_session)

        response = client.post(
            f"/api/admin/invoices/{_INVOICE_ID}/refresh-pdf",
            params={"tenant_id": tenant.id},
            headers=admin_headers(admin),
        )

        assert response.status_code == 403
        assert (
            db_session.query(InvoicePdfPayload)
            .filter(InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _INVOICE_ID)
            .first()
            is None
        )
