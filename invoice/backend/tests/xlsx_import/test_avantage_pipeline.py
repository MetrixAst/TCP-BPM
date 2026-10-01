"""End-to-end tests for the Avantage xlsx-import pipeline (parse ->
normalize -> upsert), using a synthetic workbook that reproduces the mock
Avantage file's structural quirks (see avantage_fixture.py) rather than the
real file itself."""
from datetime import date
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.xlsx_import import import_tenant_file
from app.services.xlsx_import.normalize import normalize
from app.services.xlsx_import.parsers import avantage

from .avantage_fixture import COUNTERPARTY_CACHE_FIXTURE, build_workbook_bytes


def make_trc_tenant(db_session, **overrides) -> Tenant:
    trc = TRC(name="Avantage Test", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    defaults = dict(
        trc_id=trc.id,
        name="Avantage",
        legal_name="Avantage LLP",
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
        # CounterpartyCache.data is Postgres-only JSONB, not renderable on
        # this file's in-memory SQLite db_session — see
        # counterparty_cache_service.sync_xlsx_counterparty_directory's own
        # docstring on this same constraint.
        "app.services.counterparty_cache_service.sync_xlsx_counterparty_directory",
        return_value=0,
    ):
        yield


class TestParser:
    def test_period_read_from_title_not_sheet_name(self):
        """Sheet is named "Sheet1" — period must come from the A1 text
        ("...АВГУСТ 2026"), the whole point of this parser vs maxi_mall."""
        result = avantage.parse(build_workbook_bytes())
        assert result.periods == ["2026-08"]
        assert not any("не удалось определить период" in w for w in result.warnings)

    def test_zero_charge_type_produces_no_row(self):
        result = avantage.parse(build_workbook_bytes())
        fully_paid_types = {r.charge_type for r in result.rows if r.raw_name == "Fully Paid LLP"}
        assert fully_paid_types == {"rent", "utilities"}

    def test_bin_read_from_row2_group_header_not_row3(self):
        """БИН ("Бик") has no header of its own in row 3 (the charge-types
        row) — only in row 2. Column F must still resolve to bin_value."""
        result = avantage.parse(build_workbook_bytes())
        row = next(r for r in result.rows if r.raw_name == "Fully Paid LLP")
        assert row.bin_value == "111111111111"

    def test_missing_bin_reads_as_none(self):
        result = avantage.parse(build_workbook_bytes())
        row = next(r for r in result.rows if r.raw_name == "Unknown To 1C IP")
        assert row.bin_value is None

    def test_phone_read_from_row2_group_header_not_row3(self):
        result = avantage.parse(build_workbook_bytes())
        row = next(r for r in result.rows if r.raw_name == "Fully Paid LLP")
        assert row.phone == "77011110000"

    def test_missing_phone_reads_as_none(self):
        result = avantage.parse(build_workbook_bytes())
        row = next(r for r in result.rows if r.raw_name == "Partial Payer IP")
        assert row.phone is None

    def test_broken_paid_formula_read_as_zero_with_warning(self):
        """#REF! in paid/remainder columns (the real mock file's actual
        state) must not crash the parser, but must not pass silently
        either — 0.0 there means "unknown", not "nothing paid"."""
        result = avantage.parse(build_workbook_bytes(broken_paid_formulas=True))
        row = next(r for r in result.rows if r.raw_name == "Partial Payer IP" and r.charge_type == "rent")
        assert row.paid == 0.0
        assert row.remainder == 0.0
        assert row.amounts_unreliable is True
        assert any("битой формулой" in w for w in result.warnings)

    def test_clean_file_rows_not_flagged_unreliable(self):
        result = avantage.parse(build_workbook_bytes())
        assert all(not r.amounts_unreliable for r in result.rows)

    def test_no_totals_check_for_this_format(self):
        """No "Общий свод оплат" sheet exists for this format — self-check
        is simply absent, not silently wrong."""
        result = avantage.parse(build_workbook_bytes())
        assert result.totals_check == {}

    def test_freeform_note_surfaced_as_warning(self):
        result = avantage.parse(build_workbook_bytes(note="А - сентябрь, КУ - июль"))
        assert any("А - сентябрь, КУ - июль" in w for w in result.warnings)

    def test_sheet_without_charge_title_is_ignored_not_erroring(self):
        """A workbook with no sheet whose A1 mentions "начисление" (e.g. a
        pure summary export) must not raise — it should come back empty
        with a warning, per app/api/xlsx_import.py treating this format
        mismatch as a client error (422), not a crash."""
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.title = "Sheet1"
        wb.active["A1"] = "Просто какой-то другой отчёт"
        from io import BytesIO

        buf = BytesIO()
        wb.save(buf)

        result = avantage.parse(buf.getvalue())
        assert result.rows == []
        assert result.periods == []
        assert any("начислен" in w.lower() for w in result.warnings)


class TestNormalize:
    def test_matched_vs_unmatched(self, db_session):
        tenant = make_trc_tenant(db_session)
        raw_rows = avantage.parse(build_workbook_bytes()).rows
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 27))

        by_name = {(r.ip_name, r.service_type): r for r in normalized}
        assert by_name[("Fully Paid LLP", "rent")].matched is True
        assert by_name[("Unknown To 1C IP", "rent")].matched is False
        assert by_name[("Unknown To 1C IP", "rent")].counterparty_id.startswith("virtual:")

    def test_negative_remainder_is_paid_not_unpaid(self, db_session):
        tenant = make_trc_tenant(db_session)
        raw_rows = avantage.parse(build_workbook_bytes()).rows
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 27))

        row = next(r for r in normalized if r.ip_name == "Credit Balance TOO" and r.service_type == "debt")
        assert row.status == PaymentStatus.PAID.value
        assert row.amount == -50000

    def test_unreliable_amounts_status_needs_review_not_paid(self, db_session):
        """A #REF!-broken row reads remainder=0.0, which the plain
        remainder<=tolerance rule would call PAID — amounts_unreliable must
        override that to NEEDS_REVIEW instead (see normalize._status)."""
        tenant = make_trc_tenant(db_session)
        raw_rows = avantage.parse(build_workbook_bytes(broken_paid_formulas=True)).rows
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 27))

        row = next(r for r in normalized if r.ip_name == "Partial Payer IP" and r.service_type == "rent")
        assert row.status == PaymentStatus.NEEDS_REVIEW.value

    def test_bin_match_rescues_name_that_does_not_match_cache(self, db_session):
        """"Renamed On Paper TOO" matches nothing in the cache by name — its
        БИН does (cache fullName is deliberately different), proving
        BIN-matching actually changes the outcome, not just accepted
        silently as an unused field."""
        tenant = make_trc_tenant(db_session)
        raw_rows = avantage.parse(build_workbook_bytes()).rows
        normalized = normalize(db_session, tenant, raw_rows, today=date(2026, 8, 27))

        row = next(r for r in normalized if r.source_row.raw_name == "Renamed On Paper TOO")
        assert row.matched is True
        assert row.counterparty_id == "cp-bin-match"
        # display name comes from the matched cache record, not the file's
        # own (unrecognized) name — same behavior a name-match would give.
        assert row.ip_name == "Legally Different Name TOO"


class TestFullPipeline:
    def test_import_creates_rows_with_xlsx_source(self, db_session):
        tenant = make_trc_tenant(db_session)
        summary = import_tenant_file(db_session, tenant, build_workbook_bytes())

        assert summary.rows_created == summary.rows_total
        assert summary.rows_updated == 0
        # 5 fixture tenants x 1 period, minus zero-charge rows that never
        # become rows at all (Fully Paid LLP has no debt/other; Credit
        # Balance TOO / Unknown To 1C IP / Renamed On Paper TOO have only
        # one nonzero charge type each) = 7 rows total. Only "Unknown To 1C
        # IP" is unmatched — "Renamed On Paper TOO" matches via БИН despite
        # its name matching nothing in the cache.
        assert summary.rows_total == 7
        assert summary.rows_unmatched == 1
        assert summary.rows_matched == 6
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

    def test_broken_formulas_persist_as_needs_review_not_paid(self, db_session):
        """End-to-end version of the real bug: a file with every paid/
        remainder cell broken must not land in the DB as status=paid."""
        tenant = make_trc_tenant(db_session)
        import_tenant_file(db_session, tenant, build_workbook_bytes(broken_paid_formulas=True))

        rows = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).all()
        assert rows
        assert all(r.status == PaymentStatus.NEEDS_REVIEW for r in rows)
