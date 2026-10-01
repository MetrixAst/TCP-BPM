"""Live bug found on prod 2026-08-28: analytics cards (Реестр оплат) kept
showing stale numbers after an xlsx upload replaced the underlying data —
up to 5 minutes (_ANALYTICS_CACHE_TTL_SEC), no matter how many times
"Обновить записи в реестре" was clicked, because import_tenant_file()
never invalidated PaymentService's analytics cache. The 1C sync path
(payment_sync_jobs.run_payment_sync) always did this; xlsx-import simply
never got the same call."""
from datetime import date
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.payment import PaymentFilter
from app.services.counterparty_cache_service import _INVOICE_STATUS_CACHE
from app.services.payment_service import _ANALYTICS_CACHE, PaymentService
from app.services.xlsx_import import import_tenant_file
from app.services.xlsx_import.parsers import avantage

from .avantage_fixture import COUNTERPARTY_CACHE_FIXTURE, build_workbook_bytes


def make_trc_tenant(db_session, **overrides) -> Tenant:
    trc = TRC(name="Cache Invalidation Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    defaults = dict(
        trc_id=trc.id,
        name="Cache Invalidation Test Tenant",
        legal_name="Cache Invalidation Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        xlsx_parser_key=avantage.PARSER_KEY,
        invoice_due_day=5,
    )
    defaults.update(overrides)
    tenant = Tenant(**defaults)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture(autouse=True)
def _fake_counterparty_cache():
    with patch(
        "app.services.xlsx_import.normalize._load_counterparty_cache_data",
        return_value=COUNTERPARTY_CACHE_FIXTURE,
    ), patch(
        "app.services.counterparty_cache_service.sync_xlsx_counterparty_directory",
        return_value=0,
    ):
        yield


@pytest.fixture(autouse=True)
def _clear_caches():
    """Both are module-level dicts shared across the whole test run — see
    tests/test_service_types_present.py's own comment on this same hazard
    for _ANALYTICS_CACHE."""
    _ANALYTICS_CACHE.clear()
    _INVOICE_STATUS_CACHE.clear()
    yield
    _ANALYTICS_CACHE.clear()
    _INVOICE_STATUS_CACHE.clear()


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ):
        yield


class TestXlsxImportInvalidatesAnalyticsCache:
    def test_stale_cached_analytics_replaced_after_new_upload(self, db_session):
        tenant = make_trc_tenant(db_session)
        service = PaymentService(db_session, tenant_id=tenant.id)

        # Seed a stale cached analytics result for this exact filter combo —
        # standing in for "a much bigger dataset used to exist here" (real
        # prod symptom: 408 total from an earlier, since-replaced upload).
        filters = PaymentFilter(period="2026-08", page=1, page_size=50)
        stale = service.get_analytics(filters)
        assert stale.total_invoices == 0  # nothing imported yet

        import_tenant_file(db_session, tenant, build_workbook_bytes())

        fresh = service.get_analytics(filters)
        assert fresh.total_invoices > 0
        assert fresh.total_invoices != stale.total_invoices

    def test_second_upload_with_fewer_rows_updates_the_cached_total(self, db_session):
        """The exact prod shape: a bigger dataset gets cached, then a
        smaller replacement upload lands — the cached card must reflect
        the new, smaller number afterwards, not linger on the bigger one
        that was cached before the replace."""
        tenant = make_trc_tenant(db_session)
        service = PaymentService(db_session, tenant_id=tenant.id)
        filters = PaymentFilter(period="2026-08", page=1, page_size=50)

        # Extra rows standing in for "a much bigger dataset used to be
        # here" (real prod symptom: 408 total from an earlier upload).
        for i in range(50):
            db_session.add(
                TenantPayment(
                    tenant_id=tenant.id,
                    ip_name=f"Extra {i}",
                    tenant_name=f"Extra {i}",
                    invoice_id=f"xlsx:{tenant.id}:2026-08:extra-{i}:rent",
                    invoice_date=date(2026, 8, 1),
                    due_date=date(2026, 8, 5),
                    status=PaymentStatus.UNPAID,
                    period="2026-08",
                    amount=10000,
                    paid_amount=0,
                    service_type="rent",
                    source="xlsx",
                )
            )
        db_session.commit()
        cached_before = service.get_analytics(filters)
        assert cached_before.total_invoices == 50

        # A smaller xlsx upload — full-replace (see upsert.py) deletes the
        # 50 extra rows, since they're not in this file, then this import
        # must also throw away the stale cached "50" above.
        import_tenant_file(db_session, tenant, build_workbook_bytes())

        after_replace = service.get_analytics(filters)
        assert after_replace.total_invoices != 50
        assert after_replace.total_invoices > 0
