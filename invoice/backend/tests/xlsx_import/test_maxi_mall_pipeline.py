"""End-to-end tests for the xlsx-import pipeline (parse -> normalize ->
upsert), using a synthetic workbook that reproduces the real Maxi Mall
file's structural quirks (see maxi_mall_fixture.py) rather than the real
file itself."""
from datetime import date
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.xlsx_import import import_tenant_file
from app.services.xlsx_import.normalize import normalize
from app.services.xlsx_import.parsers import maxi_mall
from app.services.xlsx_import.upsert import apply

from .maxi_mall_fixture import COUNTERPARTY_CACHE_FIXTURE, build_workbook_bytes


def make_trc_tenant(db_session, **overrides) -> Tenant:
    trc = TRC(name="Maxi Mall Test", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    defaults = dict(
        trc_id=trc.id,
        name="Maxi Mall",
        legal_name="Maxi Mall LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        xlsx_parser_key=maxi_mall.PARSER_KEY,
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


class TestParser:
    def test_parses_both_periods_and_skips_status_column_drift(self):
        """ИЮНЬ has no "Статус" column, ИЮЛЬ does — both must parse the same
        set of charge columns, proving header-name resolution (not
        fixed-index) actually works."""
        result = maxi_mall.parse(build_workbook_bytes())
        assert set(result.periods) == {"2026-06", "2026-07"}
        assert not result.warnings

    def test_totals_ito_row_excluded(self):
        result = maxi_mall.parse(build_workbook_bytes())
        names = {r.raw_name for r in result.rows}
        assert "ИТОГО ПО ТРЦ" not in names

    def test_zero_charge_type_produces_no_row(self):
        """"Fully Paid LLP" has 0/0/0 for debt and other — must not appear
        as rows for those charge types at all (see _is_zero in the
        parser)."""
        result = maxi_mall.parse(build_workbook_bytes())
        fully_paid_types = {
            r.charge_type for r in result.rows if r.raw_name == "Fully Paid LLP" and r.period == "2026-06"
        }
        assert fully_paid_types == {"rent", "utilities"}

    def test_totals_check_passes_on_consistent_file(self):
        result = maxi_mall.parse(build_workbook_bytes())
        assert result.totals_check
        assert all(check["ok"] for check in result.totals_check.values())

    def test_totals_check_catches_corrupted_summary(self):
        """The self-check exists specifically to catch a parser silently
        misreading columns — simulate that by deliberately mismatching the
        summary sheet against what the charge rows actually sum to."""
        result = maxi_mall.parse(build_workbook_bytes(corrupt_summary=True))
        failures = {k: v for k, v in result.totals_check.items() if not v["ok"]}
        assert failures
        assert any("не сошлась" in w for w in result.warnings)


class TestNormalize:
    def test_matched_vs_unmatched(self, db_session):
        tenant = make_trc_tenant(db_session)
        raw_rows = maxi_mall.parse(build_workbook_bytes()).rows
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 26))

        by_name = {(r.ip_name, r.service_type): r for r in normalized}
        assert by_name[("Fully Paid LLP", "rent")].matched is True
        assert by_name[("Unknown To 1C IP", "rent")].matched is False
        assert by_name[("Unknown To 1C IP", "rent")].counterparty_id.startswith("virtual:")

    def test_negative_remainder_is_paid_not_unpaid(self, db_session):
        """Credit Balance TOO has debt_charged=-50000, debt_paid=0,
        remainder=-50000 — a prior-period credit, not a debt. Must resolve
        to PAID, not UNPAID (see normalize._status docstring)."""
        tenant = make_trc_tenant(db_session)
        raw_rows = maxi_mall.parse(build_workbook_bytes()).rows
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 26))

        row = next(r for r in normalized if r.ip_name == "Credit Balance TOO" and r.service_type == "debt")
        assert row.status == PaymentStatus.PAID.value
        assert row.amount == -50000

    def test_overdue_when_past_due_date_and_unpaid(self, db_session):
        tenant = make_trc_tenant(db_session, invoice_due_day=5)
        raw_rows = maxi_mall.parse(build_workbook_bytes()).rows
        # 2026-06 due date (day 5) is long past by "today" = 2026-08-26.
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 26))

        row = next(
            r for r in normalized
            if r.ip_name == "Partial Payer IP" and r.service_type == "rent" and r.period == "2026-06"
        )
        assert row.status == PaymentStatus.OVERDUE.value

    def test_invoice_id_stable_across_reparse(self, db_session):
        """Same tenant/period/counterparty/type must produce the same
        invoice_id on every parse — that's what makes re-upload an update,
        not a duplicate (see upsert.py)."""
        tenant = make_trc_tenant(db_session)
        raw_rows = maxi_mall.parse(build_workbook_bytes()).rows
        first = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 26))
        second = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 26))

        first_ids = {(r.ip_name, r.service_type, r.period): r.invoice_id for r in first}
        second_ids = {(r.ip_name, r.service_type, r.period): r.invoice_id for r in second}
        assert first_ids == second_ids


class TestFullPipeline:
    def test_import_creates_rows_with_xlsx_source(self, db_session):
        tenant = make_trc_tenant(db_session)
        summary = import_tenant_file(db_session, tenant, build_workbook_bytes())

        assert summary.rows_created == summary.rows_total
        assert summary.rows_updated == 0
        # 4 fixture tenants x 2 periods, minus the zero-charge rows that
        # never become rows at all (Fully Paid LLP has no debt/other;
        # Credit Balance TOO / Unknown To 1C IP have only one nonzero
        # charge type each) = 12 rows total, of which the 2 "Unknown To 1C
        # IP" rows (one per period) are the only unmatched ones.
        assert summary.rows_total == 12
        assert summary.rows_unmatched == 2
        assert summary.rows_matched == 10
        assert summary.unmatched_names == ["Unknown To 1C IP"]
        rows = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).all()
        assert rows
        assert all(r.source == "xlsx" for r in rows)

    def test_reimport_updates_not_duplicates(self, db_session):
        tenant = make_trc_tenant(db_session)
        file_bytes = build_workbook_bytes()

        first = import_tenant_file(db_session, tenant, file_bytes)
        second = import_tenant_file(db_session, tenant, file_bytes)

        assert second.rows_created == 0
        assert second.rows_updated == first.rows_total
        total_rows = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).count()
        assert total_rows == first.rows_total

    def test_missing_parser_key_raises(self, db_session):
        tenant = make_trc_tenant(db_session, xlsx_parser_key=None)
        with pytest.raises(ValueError, match="xlsx_parser_key"):
            import_tenant_file(db_session, tenant, build_workbook_bytes())

    def test_unknown_parser_key_raises(self, db_session):
        tenant = make_trc_tenant(db_session, xlsx_parser_key="nonexistent_tc")
        with pytest.raises(ValueError, match="Неизвестный xlsx_parser_key"):
            import_tenant_file(db_session, tenant, build_workbook_bytes())
