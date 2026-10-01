"""Regression coverage for PaymentStatus.NEEDS_REVIEW (see
app/services/xlsx_import/normalize.py._status and
app/services/xlsx_import/parsers/avantage.py's #REF!-cell handling).

A needs_review row's amount/paid_amount are not trustworthy (they came from
a broken source formula) — every place downstream that used to treat "not
paid/partial/overdue" as "unpaid" by elimination must instead treat
needs_review as its own bucket, not silently fold it into unpaid (which
would misreport it exactly the same way the old PAID-by-default bug did,
just in the opposite direction)."""
from datetime import date
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.payment import PaymentFilter
from app.services.bulk_debtor_notify_service import _debtor_payments_query
from app.services.payment_service import PaymentService, _ANALYTICS_CACHE


def make_trc_tenant(db_session):
    trc = TRC(name="Needs Review Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Needs Review Test Tenant",
        legal_name="Needs Review Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def _needs_review_payment(tenant, **overrides):
    defaults = dict(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="TEMA RETAIL KZ TOO",
        invoice_id="xlsx:1:2026-08:cp-1:rent",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        period="2026-08",
        status=PaymentStatus.NEEDS_REVIEW,
        source="xlsx",
        # The real bug: a large real charge, paid_amount=0 not because
        # nothing was paid but because the source #REF! cell was read as 0.
        amount=6651840,
        paid_amount=0,
    )
    defaults.update(overrides)
    return TenantPayment(**defaults)


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ):
        yield


@pytest.fixture(autouse=True)
def _clear_analytics_cache():
    """See tests/test_service_types_present.py's own comment on this same
    fixture — _ANALYTICS_CACHE is a module-level dict keyed by tenant_id,
    which restarts at 1 in every test's fresh in-memory DB."""
    _ANALYTICS_CACHE.clear()
    yield
    _ANALYTICS_CACHE.clear()


class TestRowCoverageStatus:
    def test_needs_review_not_recomputed_as_unpaid(self, db_session):
        """Same priority tier as overdue — the stored status wins over the
        amount/paid_amount coverage recompute, which would otherwise say
        "unpaid" for a large charge with paid_amount=0."""
        trc, tenant = make_trc_tenant(db_session)
        service = PaymentService(db_session, tenant_id=tenant.id)
        row = _needs_review_payment(tenant)

        assert service._row_coverage_status(row) == PaymentStatus.NEEDS_REVIEW.value


class TestAnalyticsBucketing:
    def test_needs_review_counted_separately_not_lumped_into_unpaid(self, db_session):
        trc, tenant = make_trc_tenant(db_session)
        service = PaymentService(db_session, tenant_id=tenant.id)

        db_session.add(_needs_review_payment(tenant))
        db_session.add(
            _needs_review_payment(
                tenant,
                invoice_id="xlsx:1:2026-08:cp-2:rent",
                status=PaymentStatus.UNPAID,
                amount=100000,
                paid_amount=0,
            )
        )
        db_session.commit()

        analytics = service.get_analytics(PaymentFilter(period="2026-08", page=1, page_size=50))

        assert analytics.needs_review == 1
        assert analytics.unpaid == 1
        assert analytics.total_invoices == 2


class TestFilterByNeedsReview:
    def test_status_filter_returns_needs_review_rows(self, db_session):
        trc, tenant = make_trc_tenant(db_session)
        service = PaymentService(db_session, tenant_id=tenant.id)
        db_session.add(_needs_review_payment(tenant))
        db_session.commit()

        payments, total = service.get_payments(
            PaymentFilter(period="2026-08", status="needs_review", page=1, page_size=50)
        )

        assert total == 1
        assert payments[0].status == PaymentStatus.NEEDS_REVIEW


class TestDebtorNotifyExclusion:
    def test_needs_review_rows_excluded_from_bulk_debtor_query(self, db_session):
        """Automated WhatsApp debt reminders must never fire off data we've
        flagged as unreliable — the allowlist (.in_([UNPAID, OVERDUE])) in
        _debtor_payments_query already excludes needs_review by construction;
        this pins that guarantee down so it can't regress silently."""
        trc, tenant = make_trc_tenant(db_session)
        db_session.add(_needs_review_payment(tenant))
        db_session.add(
            _needs_review_payment(
                tenant,
                invoice_id="xlsx:1:2026-08:cp-2:rent",
                status=PaymentStatus.UNPAID,
            )
        )
        db_session.commit()

        rows = _debtor_payments_query(db_session, tenant, period="2026-08").all()

        assert len(rows) == 1
        assert rows[0].status == PaymentStatus.UNPAID
