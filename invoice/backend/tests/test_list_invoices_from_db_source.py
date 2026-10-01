"""PaymentService.list_invoices_from_db() — added a "source" field
2026-08-31 so invoice-client can tell an xlsx row (synthetic "xlsx:..."
invoice_id, no real 1C download possible) apart from a real one_c row
(real 1C GUID, downloadable via /1c/invoices/{id}/download) without
guessing from the id's shape. See app/services/xlsx_invoice_pdf.py and
the new GET /api/payments/xlsx/{invoice_id}/download endpoint that reads
this same field client-side to route to.

tenant_id=None on the service on purpose: with a tenant set, this method
also queries CounterpartyCache (Postgres-only JSONB, unrenderable on this
SQLite test DB — see conftest.py's own note) to enrich counterparty
names. None skips that block entirely (same "no tenant restriction"
meaning used everywhere scoped_tenant_id feeds into) while still
exercising the exact dict-building code path under test."""
from datetime import date

from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.payment_service import PaymentService


def make_tenant(db_session) -> Tenant:
    trc = TRC(name="Source Field Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Source Field Test Tenant",
        legal_name="Source Field Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def make_payment(db_session, tenant: Tenant, **overrides) -> TenantPayment:
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id="INV-1",
        ip_name="Арендатор",
        tenant_name="Арендатор",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        status=PaymentStatus.UNPAID,
        period="2026-08",
        amount=100000,
        source="one_c",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


class TestListInvoicesFromDbSourceField:
    def test_one_c_row_reports_source_one_c(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, invoice_id="real-guid-1", source="one_c")

        service = PaymentService(db_session, tenant_id=None)
        result = service.list_invoices_from_db(period="2026-08")

        assert len(result) == 1
        assert result[0]["source"] == "one_c"

    def test_xlsx_row_reports_source_xlsx(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(
            db_session,
            tenant,
            invoice_id="xlsx:1:2026-08:cp-1:rent",
            source="xlsx",
        )

        service = PaymentService(db_session, tenant_id=None)
        result = service.list_invoices_from_db(period="2026-08")

        assert len(result) == 1
        assert result[0]["source"] == "xlsx"
