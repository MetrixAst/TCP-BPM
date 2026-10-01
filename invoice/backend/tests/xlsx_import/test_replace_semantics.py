"""Each xlsx upload is a full replacement of that tenant's xlsx-sourced
data, not a patch — see app/services/xlsx_import/upsert.py's module
docstring for the live bug this fixes (2026-08-28: a tenant uploaded a
~150-row file, then later a 10-row file in a different format — the old
150 rows just sat there forever, upsert-by-invoice_id never touches a row
that isn't in the new file at all)."""
from unittest.mock import patch

import pytest
from openpyxl import Workbook
from io import BytesIO

from app.models.catalog import TRC, Tenant
from app.models.payment import TenantPayment
from app.services.xlsx_import import import_tenant_file
from app.services.xlsx_import.parsers import avantage, maxi_mall

from .avantage_fixture import COUNTERPARTY_CACHE_FIXTURE as AVANTAGE_CACHE
from .avantage_fixture import build_workbook_bytes as build_avantage_bytes
from .maxi_mall_fixture import COUNTERPARTY_CACHE_FIXTURE as MAXI_MALL_CACHE
from .maxi_mall_fixture import build_workbook_bytes as build_maxi_mall_bytes


def make_trc_tenant(db_session, **overrides) -> Tenant:
    trc = TRC(name="Replace Semantics Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    defaults = dict(
        trc_id=trc.id,
        name="Replace Semantics Test Tenant",
        legal_name="Replace Semantics Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
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
    # Combined cache so either fixture's tenants can match, if present.
    combined = list(MAXI_MALL_CACHE) + list(AVANTAGE_CACHE)
    with patch(
        "app.services.xlsx_import.normalize._load_counterparty_cache_data",
        return_value=combined,
    ), patch(
        "app.services.counterparty_cache_service.sync_xlsx_counterparty_directory",
        return_value=0,
    ):
        yield


class TestReplaceSemantics:
    def test_switching_file_format_deletes_stale_rows_from_previous_upload(self, db_session):
        """The exact real scenario: same tenant, first a Maxi-Mall-shaped
        file, later an Avantage-shaped one — none of the first file's rows
        should survive once a second, unrelated file lands."""
        tenant = make_trc_tenant(db_session, xlsx_parser_key=maxi_mall.PARSER_KEY)
        first = import_tenant_file(db_session, tenant, build_maxi_mall_bytes())
        assert first.rows_deleted == 0
        assert (
            db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).count()
            == first.rows_total
        )

        tenant.xlsx_parser_key = avantage.PARSER_KEY
        db_session.commit()
        second = import_tenant_file(db_session, tenant, build_avantage_bytes())

        assert second.rows_deleted == first.rows_total
        remaining = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).all()
        assert len(remaining) == second.rows_total
        assert all(r.source == "xlsx" for r in remaining)

    def test_reupload_of_unchanged_file_deletes_nothing(self, db_session):
        tenant = make_trc_tenant(db_session, xlsx_parser_key=avantage.PARSER_KEY)
        file_bytes = build_avantage_bytes()
        import_tenant_file(db_session, tenant, file_bytes)
        second = import_tenant_file(db_session, tenant, file_bytes)

        assert second.rows_deleted == 0
        assert second.rows_updated == second.rows_total

    def test_zero_row_reupload_does_not_wipe_existing_data(self, db_session):
        """A format-mismatched or corrupt file that parses to 0 rows must
        never be treated as 'replace with nothing' — that would silently
        delete a tenant's entire xlsx history on a bad upload."""
        tenant = make_trc_tenant(db_session, xlsx_parser_key=avantage.PARSER_KEY)
        first = import_tenant_file(db_session, tenant, build_avantage_bytes())
        assert first.rows_total > 0

        wb = Workbook()
        wb.active.title = "Sheet1"
        wb.active["A1"] = "not a charge sheet at all"
        buf = BytesIO()
        wb.save(buf)

        second = import_tenant_file(db_session, tenant, buf.getvalue())

        assert second.rows_total == 0
        assert second.rows_deleted == 0
        assert any("НЕ удалены" in w for w in second.warnings)
        remaining = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).count()
        assert remaining == first.rows_total
