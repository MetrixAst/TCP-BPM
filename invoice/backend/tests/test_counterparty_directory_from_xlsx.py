"""compute_xlsx_counterparty_entries() — pure logic (no DB, see its own
docstring on why: CounterpartyCache.data is Postgres-only JSONB) behind
sync_xlsx_counterparty_directory(). Turns unmatched xlsx rows into
directory entries so the Counterparties/balance tab has something to show
for an xlsx-only tenant — previously a xlsx counterparty existed nowhere
but tenant_payments.tenant_name."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.services.counterparty_cache_service import (
    compute_xlsx_counterparty_entries,
    set_counterparty_sync_done,
)
from app.services.xlsx_import.types import NormalizedRow, RawChargeRow


def _raw(name="Renter", bin_value=None) -> RawChargeRow:
    return RawChargeRow(
        raw_name=name,
        period="2026-08",
        charge_type="rent",
        charged=100000,
        paid=0,
        remainder=100000,
        bin_value=bin_value,
    )


def _normalized(*, cp_id, ip_name, matched, bin_value=None, service_type="rent") -> NormalizedRow:
    return NormalizedRow(
        tenant_id=1,
        invoice_id=f"xlsx:1:2026-08:{cp_id}:{service_type}",
        counterparty_id=cp_id,
        ip_name=ip_name,
        tenant_name=ip_name,
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        period="2026-08",
        service_type=service_type,
        amount=100000,
        paid_amount=0,
        status="unpaid",
        matched=matched,
        source_row=_raw(ip_name, bin_value),
    )


class TestComputeXlsxCounterpartyEntries:
    def test_matched_rows_excluded(self):
        """Already has a real 1C counterparty record — no synthetic entry
        needed, that would just duplicate it."""
        rows = [_normalized(cp_id="cp-real-1c", ip_name="Real Tenant", matched=True)]
        assert compute_xlsx_counterparty_entries(rows) == {}

    def test_unmatched_row_becomes_directory_entry(self):
        rows = [_normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, bin_value="123456781233")]
        entries = compute_xlsx_counterparty_entries(rows)

        assert set(entries.keys()) == {"virtual:abc123"}
        entry = entries["virtual:abc123"]
        assert entry["fullName"] == "Unknown TOO"
        assert entry["bin"] == "123456781233"
        assert entry["source"] == "xlsx"
        assert entry["invoiceCount"] == 1

    def test_multiple_service_types_same_counterparty_merge_into_one_entry(self):
        rows = [
            _normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, service_type="rent"),
            _normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, service_type="utilities"),
            _normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, service_type="debt"),
        ]
        entries = compute_xlsx_counterparty_entries(rows)

        assert len(entries) == 1
        assert entries["virtual:abc123"]["invoiceCount"] == 3

    def test_different_counterparties_stay_separate(self):
        rows = [
            _normalized(cp_id="virtual:aaa", ip_name="Tenant A", matched=False),
            _normalized(cp_id="virtual:bbb", ip_name="Tenant B", matched=False),
        ]
        entries = compute_xlsx_counterparty_entries(rows)
        assert set(entries.keys()) == {"virtual:aaa", "virtual:bbb"}

    def test_no_bin_value_defaults_to_empty_string_not_none(self):
        rows = [_normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, bin_value=None)]
        entries = compute_xlsx_counterparty_entries(rows)
        assert entries["virtual:abc123"]["bin"] == ""

    def test_bin_from_later_row_fills_in_if_first_row_had_none(self):
        """avantage.py's bin_value is per-row (same for all of one tenant's
        charge types in practice, but not guaranteed) — first non-empty one
        wins, doesn't get blanked out by a later empty one."""
        rows = [
            _normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, bin_value=None, service_type="rent"),
            _normalized(cp_id="virtual:abc123", ip_name="Unknown TOO", matched=False, bin_value="444444444444", service_type="debt"),
        ]
        entries = compute_xlsx_counterparty_entries(rows)
        assert entries["virtual:abc123"]["bin"] == "444444444444"


class TestOneCSyncPreservesXlsxDirectoryEntries:
    def test_live_1c_sync_does_not_wipe_xlsx_entries(self):
        """A tenant can have xlsx_priority=prefer_xlsx/fallback_on_1c_failure
        while 1C sync keeps running in the background (see
        xlsx_import/precedence.py) — set_counterparty_sync_done() used to
        blindly overwrite row.data with the fresh 1C payload, which would
        silently delete every xlsx-derived counterparty on the next sync.
        CounterpartyCache.data is Postgres-only JSONB (see module docstring
        elsewhere), so this fakes the row instead of hitting a real DB."""
        fake_row = SimpleNamespace(
            data=[{"id": "virtual:abc123", "fullName": "Unknown TOO", "source": "xlsx"}],
            total_from_1c=0,
            status="running",
            error=None,
            synced_at=None,
        )
        fake_db = SimpleNamespace(commit=lambda: None)
        with patch(
            "app.services.counterparty_cache_service._get_or_create_row",
            return_value=fake_row,
        ):
            set_counterparty_sync_done(
                db=fake_db,
                tenant_id=1,
                payloads=[{"id": "real-cp-1", "fullName": "Real 1C Tenant"}],
                total=1,
            )

        ids = {item["id"] for item in fake_row.data}
        assert "real-cp-1" in ids
        assert "virtual:abc123" in ids
        assert fake_row.status == "done"
