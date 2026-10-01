"""GET /api/payments/1c/invoices/{invoice_id}/download — live bug found
2026-08-28 (real prod report: Maxi Mall downloads failing with a generic
500 "Попробуйте позже" for почти every invoice). Root cause: the
try/except in download_1c_invoice had no `except HTTPException: raise`
before its catch-all `except Exception` — so every intentional
HTTPException raised inside the try (missing counterparty_id -> 400,
assert_invoice_belongs_to_counterparty -> 404/403) fell through to the
generic handler and came back as a misleading 500 instead of its real
status code, masking the actual reason. Confirmed by reproducing directly
against a real local 1C-connected test tenant (Maxi Mall, org 119) before
this fix: HTTP 500 "Не удалось скачать счёт из 1С" even though the actual
exception was `HTTPException(404, "Счёт не найден в 1С")`.

get_1c_invoices() (the sibling list endpoint just above this one in the
same file) already has the `except HTTPException: raise` guard — this
file's fix brings the download endpoint in line with that existing,
correct convention."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.security import create_trc_portal_token
from app.models.catalog import TRC, Tenant


def make_trc_tenant(db_session) -> tuple[TRC, Tenant]:
    trc = TRC(name="Download Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Download Test Tenant",
        legal_name="Download Test Tenant LLP",
        one_c_login="odata.user",
        one_c_password="secret",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def _auth_headers(trc: TRC) -> dict:
    return {"Authorization": f"Bearer {create_trc_portal_token(trc.id)}"}


def _fake_integration() -> MagicMock:
    integration = MagicMock()
    integration.client.access_token = "already-authenticated"
    integration.close = MagicMock()
    return integration


class TestHTTPExceptionNotMaskedAs500:
    def test_missing_counterparty_id_returns_400_not_500(self, client, db_session):
        trc, tenant = make_trc_tenant(db_session)

        with patch(
            "app.api.payments.get_integration_for_tenant",
            return_value=_fake_integration(),
        ), patch(
            "app.api.payments.get_tenant_by_id",
            return_value=tenant,
        ):
            response = client.get(
                f"/api/payments/1c/invoices/some-invoice-id/download?tenant_id={tenant.id}",
                headers=_auth_headers(trc),
            )

        assert response.status_code == 400
        assert "counterparty_id" in response.json()["detail"]

    def test_invoice_not_found_in_1c_returns_404_not_500(self, client, db_session):
        trc, tenant = make_trc_tenant(db_session)

        with patch(
            "app.api.payments.get_integration_for_tenant",
            return_value=_fake_integration(),
        ), patch(
            "app.api.payments.get_tenant_by_id",
            return_value=tenant,
        ), patch(
            "app.api.payments.assert_invoice_belongs_to_counterparty",
            side_effect=HTTPException(status_code=404, detail="Счёт не найден в 1С"),
        ):
            response = client.get(
                f"/api/payments/1c/invoices/some-invoice-id/download"
                f"?tenant_id={tenant.id}&counterparty_id=some-cp-id",
                headers=_auth_headers(trc),
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Счёт не найден в 1С"

    def test_invoice_belongs_to_different_counterparty_returns_403_not_500(self, client, db_session):
        trc, tenant = make_trc_tenant(db_session)

        with patch(
            "app.api.payments.get_integration_for_tenant",
            return_value=_fake_integration(),
        ), patch(
            "app.api.payments.get_tenant_by_id",
            return_value=tenant,
        ), patch(
            "app.api.payments.assert_invoice_belongs_to_counterparty",
            side_effect=HTTPException(status_code=403, detail="Счёт не принадлежит указанному контрагенту"),
        ):
            response = client.get(
                f"/api/payments/1c/invoices/some-invoice-id/download"
                f"?tenant_id={tenant.id}&counterparty_id=wrong-cp-id",
                headers=_auth_headers(trc),
            )

        assert response.status_code == 403

    def test_genuinely_unexpected_error_still_returns_500(self, client, db_session):
        """The fix must not swallow real bugs into a 4xx either — only
        HTTPException gets the pass-through, anything else still 500s."""
        trc, tenant = make_trc_tenant(db_session)

        with patch(
            "app.api.payments.get_integration_for_tenant",
            return_value=_fake_integration(),
        ), patch(
            "app.api.payments.get_tenant_by_id",
            return_value=tenant,
        ), patch(
            "app.api.payments.assert_invoice_belongs_to_counterparty",
            side_effect=RuntimeError("something genuinely unexpected"),
        ):
            response = client.get(
                f"/api/payments/1c/invoices/some-invoice-id/download"
                f"?tenant_id={tenant.id}&counterparty_id=some-cp-id",
                headers=_auth_headers(trc),
            )

        assert response.status_code == 500
