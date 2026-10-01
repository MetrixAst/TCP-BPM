"""POST /api/notifications/send — xlsx-sourced payments (source="xlsx")
previously could never be sent via WhatsApp at all: integration.client is
None for a pure-xlsx tenant (no 1C login/password/Nova org configured),
and the old code only ever fell back to a *cached 1C* PDF in that case —
which can't exist for a synthetic "xlsx:..." invoice_id (see
app/services/xlsx_invoice_pdf.py's module docstring) — so every attempt
hit the final `raise HTTPException(503, ...)`.

app.api.notifications._resolve_xlsx_payment_for_send() is the new branch
point; these tests exercise it through the real HTTP endpoint rather than
in isolation, since its correctness depends on exactly where it sits
relative to the pre-existing integration.client / payment_trusted logic
(see the extensive comments in send_notification itself)."""
from datetime import date
from unittest.mock import patch

import pytest

from app.core.security import (
    create_access_token,
    create_tenant_portal_token,
)
from app.models.catalog import TRC, AdminUser, CounterpartyPhone, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services import whatsapp_jobs


def make_trc(db_session, **overrides) -> TRC:
    defaults = dict(name="Send Xlsx Test TRC", is_active=True)
    defaults.update(overrides)
    trc = TRC(**defaults)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def make_tenant(db_session, trc: TRC, **overrides) -> Tenant:
    """No one_c_login/password, no nova_organization_id -> a pure-xlsx
    tenant: build_integration_for_tenant() gives it integration.client=None
    (see app/services/tenant_1c.py)."""
    defaults = dict(
        trc_id=trc.id,
        name="Send Xlsx Test Tenant",
        legal_name="Send Xlsx Test Tenant LLP",
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


@pytest.fixture(autouse=True)
def _fake_whatsapp_transport():
    """Never hit real Green API from a test — same mocking point already
    used by test_whatsapp_resilience.py."""
    fake_whatsapp = type(
        "FakeWA",
        (),
        {
            "send_message": staticmethod(lambda **kw: True),
            "last_id_message": "3EB0FAKEXLSXID",
        },
    )()
    with patch.object(whatsapp_jobs, "get_whatsapp_for_tenant", return_value=fake_whatsapp):
        yield


def _mock_render(tmp_path, name="invoice.pdf", content=b"%PDF-1.4 fake xlsx invoice"):
    pdf_path = tmp_path / name
    pdf_path.write_bytes(content)
    return patch("app.api.notifications.render_xlsx_invoice_pdf", return_value=str(pdf_path))


class TestSendXlsxInvoiceViaPaymentId:
    def test_sends_and_marks_delivered(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        with _mock_render(tmp_path):
            resp = client.post(
                "/api/notifications/send",
                json={
                    "payment_id": payment.id,
                    "notification_type": "overdue",
                    "phone_number": "+77001234567",
                },
                params={"tenant_id": tenant.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["whatsapp_sent"] is True

    def test_missing_supplier_requisites_returns_422(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        from app.client_1c.exceptions import MissingSupplierRequisitesError

        with patch(
            "app.api.notifications.render_xlsx_invoice_pdf",
            side_effect=MissingSupplierRequisitesError("нет IIK/BIK"),
        ):
            resp = client.post(
                "/api/notifications/send",
                json={
                    "payment_id": payment.id,
                    "notification_type": "overdue",
                    "phone_number": "+77001234567",
                },
                params={"tenant_id": tenant.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 422

    def test_phone_mismatch_with_admin_recorded_phone_returns_403(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        payment = make_xlsx_payment(db_session, tenant)
        db_session.add(
            CounterpartyPhone(
                trc_id=trc.id,
                one_c_counterparty_id="cp-1",
                phone="+77009998877",
            )
        )
        db_session.commit()
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        with _mock_render(tmp_path):
            resp = client.post(
                "/api/notifications/send",
                json={
                    "payment_id": payment.id,
                    "notification_type": "overdue",
                    "phone_number": "+77001111111",
                },
                params={"tenant_id": tenant.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 403

    def test_other_tenant_portal_login_cannot_send_via_payment_id(self, client, db_session, tmp_path):
        """Regression: found live while writing this test — payment_id was
        never checked against the resolved tenant_id at all, letting tenant
        B's login send tenant A's payment with tenant B's own record used as
        supplier. Fixed in send_notification right where payment_id is
        first loaded (not xlsx-specific — this protects every send path)."""
        trc1 = make_trc(db_session, name="Trc One")
        trc2 = make_trc(db_session, name="Trc Two")
        tenant1 = make_tenant(db_session, trc1, name="T1", legal_name="T1 LLP")
        tenant2 = make_tenant(db_session, trc2, name="T2", legal_name="T2 LLP")
        payment = make_xlsx_payment(db_session, tenant1)
        token = create_tenant_portal_token(tenant_id=tenant2.id, trc_id=trc2.id)

        with _mock_render(tmp_path) as mock_render:
            resp = client.post(
                "/api/notifications/send",
                json={
                    "payment_id": payment.id,
                    "notification_type": "overdue",
                    "phone_number": "+77001234567",
                },
                params={"tenant_id": tenant2.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 403
        mock_render.assert_not_called()


class TestSendXlsxInvoiceViaCounterpartyLookup:
    """No payment_id given at all — mirrors the 'send from counterparty
    card' UI flow (openNotifyModal without paymentId, see
    useCounterpartyNotify.ts). Must fall back to a DB lookup by
    counterparty (+service_type) instead of the 503 it used to hit."""

    def test_resolves_latest_xlsx_payment_by_counterparty(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        make_xlsx_payment(db_session, tenant, invoice_id="xlsx:1:2026-07:cp-1:rent", period="2026-07")
        latest = make_xlsx_payment(db_session, tenant, invoice_id="xlsx:1:2026-08:cp-1:rent", period="2026-08")
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        with _mock_render(tmp_path) as mock_render:
            resp = client.post(
                "/api/notifications/send",
                json={
                    "notification_type": "overdue",
                    "phone_number": "+77001234567",
                    "counterparty_id": "cp-1",
                },
                params={"tenant_id": tenant.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        rendered_payment = mock_render.call_args[0][1]
        assert rendered_payment.id == latest.id

    def test_service_type_narrows_the_match(self, client, db_session, tmp_path):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        rent = make_xlsx_payment(
            db_session, tenant, invoice_id="xlsx:1:2026-08:cp-1:rent", service_type="rent"
        )
        make_xlsx_payment(
            db_session,
            tenant,
            invoice_id="xlsx:1:2026-08:cp-1:utilities",
            service_type="utilities",
        )
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        with _mock_render(tmp_path) as mock_render:
            resp = client.post(
                "/api/notifications/send",
                json={
                    "notification_type": "overdue",
                    "phone_number": "+77001234567",
                    "counterparty_id": "cp-1",
                    "service_type": "rent",
                },
                params={"tenant_id": tenant.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        rendered_payment = mock_render.call_args[0][1]
        assert rendered_payment.id == rent.id

    def test_no_matching_xlsx_payment_and_no_1c_returns_503(self, client, db_session):
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        token = create_tenant_portal_token(tenant_id=tenant.id, trc_id=trc.id)

        resp = client.post(
            "/api/notifications/send",
            json={
                "notification_type": "overdue",
                "phone_number": "+77001234567",
                "counterparty_id": "cp-does-not-exist",
            },
            params={"tenant_id": tenant.id},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 503

    def test_admin_can_resolve_across_tenants_only_with_explicit_tenant_id(
        self, client, db_session, tmp_path
    ):
        """find_latest_xlsx_payment refuses tenant_id=None outright (see its
        own docstring) — an admin request must still pass a concrete
        tenant_id query param to reach the xlsx fallback at all."""
        trc = make_trc(db_session)
        tenant = make_tenant(db_session, trc)
        make_xlsx_payment(db_session, tenant)
        headers = _admin_headers(db_session)

        with _mock_render(tmp_path):
            resp = client.post(
                "/api/notifications/send",
                json={
                    "notification_type": "overdue",
                    "phone_number": "+77001234567",
                    "counterparty_id": "cp-1",
                },
                params={"tenant_id": tenant.id},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
