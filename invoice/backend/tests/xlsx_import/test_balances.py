"""recompute_xlsx_balances() — Долг/Аванс/Нетто computed from imported xlsx
rows (amount - paid_amount per row, summed per counterparty), plus the
guard in counterparty_balance_service.replace_balances_for_tenant that
keeps the next 1C balance sync from silently wiping these rows."""
from datetime import date

import pytest

from app.models.catalog import TRC, Tenant
from app.models.counterparty_balance import CounterpartyBalance
from app.models.payment import PaymentStatus, TenantPayment
from app.services.counterparty_balance_service import replace_balances_for_tenant
from app.services.xlsx_import.balances import recompute_xlsx_balances


def make_tenant(db_session) -> Tenant:
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
    return tenant


def make_payment(db_session, tenant, *, cp_id, invoice_id, amount, paid_amount, name="Renter", **overrides):
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=invoice_id,
        counterparty_id=cp_id,
        ip_name=name,
        tenant_name=name,
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        status=PaymentStatus.UNPAID,
        period="2026-08",
        amount=amount,
        paid_amount=paid_amount,
        service_type="rent",
        source="xlsx",
    )
    defaults.update(overrides)
    p = TenantPayment(**defaults)
    db_session.add(p)
    db_session.commit()
    return p


class TestRecomputeXlsxBalances:
    def test_positive_remainder_is_debit(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, cp_id="cp-1", invoice_id="INV-1", amount=100000, paid_amount=40000)

        saved = recompute_xlsx_balances(db_session, tenant.id)

        assert saved == 1
        row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-1"
        ).first()
        assert float(row.debit) == 60000
        assert float(row.credit) == 0
        assert row.source == "xlsx"

    def test_negative_remainder_is_credit(self, db_session):
        """Overpaid — a real advance, not a debt."""
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, cp_id="cp-1", invoice_id="INV-1", amount=50000, paid_amount=80000)

        recompute_xlsx_balances(db_session, tenant.id)

        row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-1"
        ).first()
        assert float(row.debit) == 0
        assert float(row.credit) == 30000

    def test_sums_across_multiple_rows_and_periods(self, db_session):
        """A second upload adding a new period must accumulate onto the
        counterparty's total, not replace it — see balances.py docstring."""
        tenant = make_tenant(db_session)
        make_payment(
            db_session, tenant, cp_id="cp-1", invoice_id="INV-JUN", amount=100000, paid_amount=100000,
            period="2026-06",
        )
        make_payment(
            db_session, tenant, cp_id="cp-1", invoice_id="INV-JUL", amount=100000, paid_amount=20000,
            period="2026-07",
        )

        recompute_xlsx_balances(db_session, tenant.id)

        row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-1"
        ).first()
        assert float(row.debit) == 80000  # only the July shortfall is outstanding

    def test_ignores_one_c_sourced_rows(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(
            db_session, tenant, cp_id="cp-1", invoice_id="1C-DOC", amount=999999, paid_amount=0,
            source="one_c",
        )

        saved = recompute_xlsx_balances(db_session, tenant.id)

        assert saved == 0

    def test_reexisting_row_gets_updated_not_duplicated(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, cp_id="cp-1", invoice_id="INV-1", amount=100000, paid_amount=0)
        recompute_xlsx_balances(db_session, tenant.id)

        # Re-upload corrects the payment (e.g. late payment recorded).
        row = db_session.query(TenantPayment).filter(TenantPayment.invoice_id == "INV-1").first()
        row.paid_amount = 100000
        db_session.commit()
        recompute_xlsx_balances(db_session, tenant.id)

        rows = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-1"
        ).all()
        assert len(rows) == 1
        assert float(rows[0].debit) == 0


class TestOneCSyncDoesNotWipeXlsxBalances:
    def test_xlsx_row_survives_full_tenant_resync(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, cp_id="cp-xlsx", invoice_id="INV-1", amount=50000, paid_amount=0)
        recompute_xlsx_balances(db_session, tenant.id)

        # A live 1C balance sync for this tenant runs afterwards — it knows
        # nothing about cp-xlsx (not in its payload) and has its own data
        # for an unrelated 1C counterparty.
        replace_balances_for_tenant(
            db_session, tenant.id,
            rows=[{"counterparty_id": "cp-1c", "counterparty_name": "1C Renter", "debit": 200000, "credit": 0}],
        )

        xlsx_row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-xlsx"
        ).first()
        assert xlsx_row is not None
        assert float(xlsx_row.debit) == 50000  # untouched by the 1C sync

        one_c_row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-1c"
        ).first()
        assert one_c_row is not None
        assert one_c_row.source == "one_c"

    def test_one_c_payload_for_same_counterparty_does_not_overwrite_xlsx(self, db_session):
        """The matched-counterparty case: 1C's own live balance sync has
        fresher-looking data for the SAME counterparty_id excel already
        claimed — excel must still win (no PK collision, no silent
        overwrite either)."""
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, cp_id="cp-shared", invoice_id="INV-1", amount=50000, paid_amount=0)
        recompute_xlsx_balances(db_session, tenant.id)

        replace_balances_for_tenant(
            db_session, tenant.id,
            rows=[{"counterparty_id": "cp-shared", "counterparty_name": "1C Name", "debit": 999999, "credit": 0}],
        )

        row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-shared"
        ).all()
        assert len(row) == 1  # no duplicate PK row
        assert float(row[0].debit) == 50000
        assert row[0].source == "xlsx"


class TestStaleBalanceCleanup:
    """Same live bug as upsert.py (2026-08-28): a counterparty with no more
    source="xlsx" tenant_payments rows (superseded by a new/different file)
    must not keep showing a stale debt/advance figure forever."""

    def test_counterparty_gone_from_new_upload_loses_its_balance_row(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, cp_id="cp-old", invoice_id="INV-OLD", amount=50000, paid_amount=0)
        recompute_xlsx_balances(db_session, tenant.id)
        assert (
            db_session.query(CounterpartyBalance)
            .filter(CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-old")
            .first()
            is not None
        )

        # Simulates upsert.apply() having already deleted cp-old's stale
        # tenant_payments row as part of the new upload's full replace, and
        # inserted a row for a completely different counterparty instead.
        db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).delete()
        make_payment(db_session, tenant, cp_id="cp-new", invoice_id="INV-NEW", amount=30000, paid_amount=30000)
        recompute_xlsx_balances(db_session, tenant.id)

        assert (
            db_session.query(CounterpartyBalance)
            .filter(CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-old")
            .first()
            is None
        )
        assert (
            db_session.query(CounterpartyBalance)
            .filter(CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-new")
            .first()
            is not None
        )

    def test_one_c_sourced_balance_untouched_by_xlsx_cleanup(self, db_session):
        """The stale-cleanup filters by source="xlsx" — a 1C-sourced balance
        row for an unrelated counterparty must survive even when this
        tenant's xlsx data goes to zero."""
        tenant = make_tenant(db_session)
        replace_balances_for_tenant(
            db_session, tenant.id,
            rows=[{"counterparty_id": "cp-1c", "counterparty_name": "1C Renter", "debit": 200000, "credit": 0}],
        )

        recompute_xlsx_balances(db_session, tenant.id)  # no xlsx rows at all

        one_c_row = db_session.query(CounterpartyBalance).filter(
            CounterpartyBalance.tenant_id == tenant.id, CounterpartyBalance.counterparty_id == "cp-1c"
        ).first()
        assert one_c_row is not None
        assert one_c_row.source == "one_c"
