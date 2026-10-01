"""prefer_xlsx: a 1C sync and an xlsx import can both leave a row for the
same (tenant, period, counterparty_id, service_type) in tenant_payments —
they never collide by invoice_id (see upsert.py), so nothing at the DB
level stops both from existing at once. Without exclude_shadowed_one_c_rows
(precedence.py), that means: the registry shows what looks like two
invoices for one month's rent, and bulk debtor notify could WhatsApp the
same tenant twice for the same debt. These tests pin that it doesn't.

Product decision (2026-08-26): 1C sync keeps running in the background even
for prefer_xlsx tenants (not disabled) — precedence is a read-time filter,
not a write-time skip."""
from datetime import date
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.payment import PaymentFilter
from app.services.bulk_debtor_notify_service import count_debtor_candidates
from app.services.counterparty_status_db import latest_invoice_status_by_counterparty_from_db
from app.services.payment_service import PaymentService, _ANALYTICS_CACHE


@pytest.fixture(autouse=True)
def _clear_analytics_cache():
    _ANALYTICS_CACHE.clear()
    yield
    _ANALYTICS_CACHE.clear()


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ), patch(
        "app.services.counterparty_status_db._load_cache_data",
        return_value=[],
    ):
        yield


def make_tenant(db_session, *, xlsx_priority: str) -> Tenant:
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
        xlsx_priority=xlsx_priority,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def make_payment(db_session, tenant, *, source, invoice_id, status, **overrides):
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=invoice_id,
        counterparty_id="cp-shared",
        ip_name="Shared Renter",
        tenant_name="Shared Renter",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        status=status,
        period="2026-08",
        amount=100000,
        paid_amount=0,
        service_type="rent",
        source=source,
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    return payment


def make_shadow_pair(db_session, tenant, *, one_c_status=PaymentStatus.OVERDUE, xlsx_status=PaymentStatus.PAID):
    """A 1C row and an xlsx row for the exact same (period, counterparty,
    service_type) — the scenario precedence.py exists to resolve.

    paid_amount is set consistent with each row's status because
    counterparty_status_db._payment_row_status recomputes paid/partial/
    unpaid from amount/paid_amount coverage rather than trusting the stored
    status column directly (see its own docstring) — an inconsistent
    fixture (status=PAID, paid_amount=0) would silently read back as
    "unpaid" regardless of what precedence.py did."""
    one_c_paid = 100000 if one_c_status == PaymentStatus.PAID else 0
    xlsx_paid = 100000 if xlsx_status == PaymentStatus.PAID else 0
    make_payment(
        db_session, tenant, source="one_c", invoice_id="1C-DOC-1",
        status=one_c_status, paid_amount=one_c_paid,
    )
    make_payment(
        db_session, tenant, source="xlsx", invoice_id="xlsx:t:2026-08:cp-shared:rent",
        status=xlsx_status, paid_amount=xlsx_paid,
    )


class TestRegistryAndAnalytics:
    def test_prefer_xlsx_hides_shadowed_one_c_row(self, db_session):
        tenant = make_tenant(db_session, xlsx_priority="prefer_xlsx")
        make_shadow_pair(db_session, tenant)

        service = PaymentService(db_session, tenant_id=tenant.id)
        payments, total = service.get_payments(PaymentFilter(period="2026-08"))

        assert total == 1
        assert payments[0].source == "xlsx"

    def test_non_prefer_xlsx_shows_both_rows(self, db_session):
        """disabled/fallback_on_1c_failure tenants never had an xlsx row
        materialize in the first place in real usage, but if one somehow
        exists, precedence must not silently apply — only prefer_xlsx opts
        into hiding 1C rows."""
        tenant = make_tenant(db_session, xlsx_priority="fallback_on_1c_failure")
        make_shadow_pair(db_session, tenant)

        service = PaymentService(db_session, tenant_id=tenant.id)
        payments, total = service.get_payments(PaymentFilter(period="2026-08"))

        assert total == 2


class TestBulkDebtorNotify:
    def test_shadowed_one_c_debtor_row_excluded(self, db_session):
        """1C still thinks this is overdue (stale); excel already shows it
        paid. Must not count as a debtor to notify — sending a WhatsApp
        debt reminder here would be simply wrong, not just a duplicate."""
        tenant = make_tenant(db_session, xlsx_priority="prefer_xlsx")
        make_shadow_pair(
            db_session, tenant,
            one_c_status=PaymentStatus.OVERDUE,
            xlsx_status=PaymentStatus.PAID,
        )

        count = count_debtor_candidates(db_session, tenant_id=tenant.id, period="2026-08")

        assert count == 0

    def test_unshadowed_debtor_row_still_counted(self, db_session):
        """A counterparty that only exists in 1C (never touched by the
        xlsx file) must still generate a normal reminder."""
        tenant = make_tenant(db_session, xlsx_priority="prefer_xlsx")
        make_payment(
            db_session, tenant,
            source="one_c", invoice_id="1C-DOC-2", status=PaymentStatus.OVERDUE,
            counterparty_id="cp-1c-only",
        )

        count = count_debtor_candidates(db_session, tenant_id=tenant.id, period="2026-08")

        assert count == 1


class TestCounterpartyStatus:
    def test_xlsx_status_wins_over_higher_priority_stale_one_c_status(self, db_session):
        """Without precedence filtering, this function's own tie-break
        (overdue > partial > unpaid > paid) would pick the STALE 1C
        "overdue" row over the correct, fresher xlsx "paid" row — actively
        surfacing the wrong status, not just a harmless duplicate."""
        tenant = make_tenant(db_session, xlsx_priority="prefer_xlsx")
        make_shadow_pair(
            db_session, tenant,
            one_c_status=PaymentStatus.OVERDUE,
            xlsx_status=PaymentStatus.PAID,
        )

        result = latest_invoice_status_by_counterparty_from_db(
            db_session, tenant_id=tenant.id, period="2026-08"
        )

        assert result["cp-shared"]["paymentStatus"] == "paid"
