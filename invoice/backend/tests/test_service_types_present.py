"""PaymentAnalytics.service_types_present — which service_type values have at
least one invoice for the current tenant/period, independent of the
currently-selected service_type filter.

Added alongside the "debt"/"other" service types (xlsx import for Maxi
Mall): most tenants never have those, or signage/assp — the frontend uses
this list to hide filter options with zero data instead of always showing
the full 7-type list (see InvoiceRegistryTable.tsx)."""

from datetime import date
from unittest.mock import patch

import pytest

from app.core.security import create_tenant_portal_token
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.payment import PaymentFilter
from app.services.payment_service import PaymentService, _ANALYTICS_CACHE


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ):
        yield


@pytest.fixture(autouse=True)
def _clear_analytics_cache():
    """_ANALYTICS_CACHE is a module-level dict shared across the whole test
    run, keyed by tenant_id (autoincrement — restarts at 1 in every test's
    fresh in-memory DB). Without clearing it, a cached entry from an earlier
    test's tenant_id=1 could leak into this one and make results depend on
    test order."""
    _ANALYTICS_CACHE.clear()
    yield
    _ANALYTICS_CACHE.clear()


def make_trc_tenant(db_session):
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
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def make_payment(db_session, tenant, invoice_id, service_type, **overrides):
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=invoice_id,
        ip_name="Renter",
        tenant_name="Renter",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 10),
        status=PaymentStatus.UNPAID,
        period="2026-08",
        amount=100000,
        service_type=service_type,
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    return payment


def test_present_types_reflect_only_what_exists(db_session):
    _trc, tenant = make_trc_tenant(db_session)
    make_payment(db_session, tenant, "INV-1", "rent")
    make_payment(db_session, tenant, "INV-2", "utilities")
    make_payment(db_session, tenant, "INV-3", "debt")
    # No "operations", "signage", "assp", "other" rows at all.

    service = PaymentService(db_session, tenant_id=tenant.id)
    analytics = service.get_analytics(PaymentFilter(period="2026-08"))

    assert set(analytics.service_types_present) == {"rent", "utilities", "debt"}
    # SERVICE_TYPE_ORDER order, not insertion order.
    assert analytics.service_types_present == ["rent", "utilities", "debt"]


def test_present_types_independent_of_selected_filter(db_session):
    """Selecting one type in the table filter must not hide the others from
    the filter dropdown itself on the next render — that would make already-
    filtered-away options permanently unreachable without a page reload."""
    _trc, tenant = make_trc_tenant(db_session)
    make_payment(db_session, tenant, "INV-1", "rent")
    make_payment(db_session, tenant, "INV-2", "other")

    service = PaymentService(db_session, tenant_id=tenant.id)
    analytics = service.get_analytics(
        PaymentFilter(period="2026-08", service_type="rent")
    )

    assert set(analytics.service_types_present) == {"rent", "other"}


def test_unknown_excluded_from_present_types(db_session):
    _trc, tenant = make_trc_tenant(db_session)
    make_payment(db_session, tenant, "INV-1", "unknown")

    service = PaymentService(db_session, tenant_id=tenant.id)
    analytics = service.get_analytics(PaymentFilter(period="2026-08"))

    assert analytics.service_types_present == []


def test_multi_type_row_splits_into_atomic_types(db_session):
    """service_type can be a comma-joined string on a single invoice
    (format_service_types_label) — presence must still report each atomic
    type, not the raw joined string."""
    _trc, tenant = make_trc_tenant(db_session)
    make_payment(db_session, tenant, "INV-1", "rent,utilities")

    service = PaymentService(db_session, tenant_id=tenant.id)
    analytics = service.get_analytics(PaymentFilter(period="2026-08"))

    assert set(analytics.service_types_present) == {"rent", "utilities"}
