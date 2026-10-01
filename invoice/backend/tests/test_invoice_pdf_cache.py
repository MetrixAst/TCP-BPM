"""invoice_pdf_cache — structured-payload cache for invoice PDF generation,
so a repeat view of an already-seen invoice never needs to hit live 1C.
See app/models/invoice_pdf_payload.py and app/services/invoice_pdf_cache.py
module docstrings for the full design rationale (agreed 2026-08-28, see
memory invoice_pdf_payload_cache_plan)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.client_1c.exceptions import ValidationError
from app.models.catalog import TRC, Tenant
from app.models.invoice_pdf_payload import InvoicePdfPayload
from app.services.invoice_pdf_cache import (
    FORCE_REFRESH_COOLDOWN,
    LINE_ITEMS_FRESHNESS_TTL,
    can_attempt_force_refresh,
    get_cached_payload,
    is_payload_cache_stale,
    is_valid_pdf_payload,
    mark_force_refresh_attempted,
    store_payload_if_valid,
    strip_tenant_sourced_fields,
)

_REAL_INVOICE_ID = "f49e3940-9563-11f1-b522-4c526260eadb"
_REAL_CP_ID = "f49e393a-9563-11f1-b522-4c526260eadb"


def _valid_payload(**overrides) -> dict:
    payload = {
        "id": _REAL_INVOICE_ID,
        "number": "18490",
        "date": "2026-08-01",
        "counterparty_id": _REAL_CP_ID,
        "counterparty_name": "Тестовый Арендатор ТОО",
        "amount": 500000,
        "currency": "KZT",
        "items": [{"name": "Аренда за август", "quantity": 1, "price": 500000, "amount": 500000}],
        # These 1C-sourced supplier fields should get stripped before caching.
        "supplier_name": "1C Original Supplier",
        "supplier_iik": "KZ1C00000000000001",
        "supplier_bik": "1C_BIK",
        "supplier": {"name": "1C Original Supplier", "iik": "KZ1C00000000000001"},
    }
    payload.update(overrides)
    return payload


def make_tenant(db_session, *, trc_name="PDF Cache Test TRC", **overrides) -> Tenant:
    trc = TRC(name=trc_name, is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    defaults = dict(
        trc_id=trc.id,
        name="PDF Cache Test Tenant",
        legal_name="PDF Cache Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        invoice_iik="KZ999CURRENTACCOUNT",
        invoice_bank_bik="CURRENTBIK",
        invoice_bank_name="Current Bank",
        invoice_kbe="17",
    )
    defaults.update(overrides)
    tenant = Tenant(**defaults)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


class TestIsValidPdfPayload:
    def test_complete_payload_is_valid(self):
        assert is_valid_pdf_payload(_valid_payload()) is True

    def test_none_is_invalid(self):
        assert is_valid_pdf_payload(None) is False

    def test_empty_dict_is_invalid(self):
        assert is_valid_pdf_payload({}) is False

    @pytest.mark.parametrize("missing_key", ["number", "date", "counterparty_id", "amount", "items"])
    def test_missing_required_field_is_invalid(self, missing_key):
        payload = _valid_payload()
        payload.pop(missing_key)
        assert is_valid_pdf_payload(payload) is False

    def test_empty_items_list_is_invalid(self):
        """The real bug this gate exists for: a degraded rehydrate that
        returns a header but no line items (one of ~5 independent fallback
        tiers came back empty) must not be mistaken for success."""
        assert is_valid_pdf_payload(_valid_payload(items=[])) is False

    def test_missing_supplier_requisites_does_not_fail_validity(self):
        """Supplier banks are no longer part of what 1C is required to
        provide (see TENANT_SOURCED_KEYS) — a payload with real invoice
        content but no supplier_iik must still be cacheable."""
        payload = _valid_payload()
        for key in ("supplier_name", "supplier_iik", "supplier_bik", "supplier"):
            payload.pop(key, None)
        assert is_valid_pdf_payload(payload) is True


class TestStripTenantSourcedFields:
    """Real bug found 2026-09-01: strip_tenant_sourced_fields used to wipe
    every TENANT_SOURCED_KEYS field unconditionally, regardless of whether
    the value actually came from 1C (OData org lookup, Nova COM/MCP
    enrichment — genuine, stable 1C content) or from Tenant.invoice_*
    fallback (the only case that legitimately needs re-freshing per read).
    Since migration f6a7b8c9d0e1 (2026-05-29) wiped every real tenant's
    invoice_iik/etc to NULL with the explicit rationale "for PDF, banks
    come from 1C", the unconditional strip was discarding exactly the real
    1C bank data that made the FIRST download of an invoice succeed — the
    SECOND view then either hard-failed (Nova: MissingSupplierRequisitesError,
    see nova_buh_1c_client.py's cache-hit gate) or silently rendered a PDF
    with blank bank fields (OData: no such gate on its cache-hit path)."""

    def test_without_tenant_falls_back_to_unconditional_strip(self):
        """Defensive default for a hypothetical caller with no tenant to
        compare against — real callers (nova_buh_1c_client.py,
        odata_1c_client.py) always pass one."""
        cleaned = strip_tenant_sourced_fields(_valid_payload())
        for key in ("supplier_name", "supplier_iik", "supplier_bik", "supplier"):
            assert key not in cleaned

    def test_keeps_1c_native_fields_regardless_of_tenant_arg(self):
        cleaned = strip_tenant_sourced_fields(_valid_payload())
        assert cleaned["number"] == "18490"
        assert cleaned["counterparty_id"] == _REAL_CP_ID
        assert cleaned["items"]

    def test_value_differing_from_tenant_fallback_is_preserved(self, db_session):
        """The actual bug fix: a bank value that came from 1C itself (here,
        deliberately different from the tenant's own fallback value) must
        survive into the cache — it's real, stable 1C content, not
        something that goes stale when an admin edits the tenant record."""
        tenant = make_tenant(db_session, invoice_iik="KZ999CURRENTACCOUNT", invoice_bank_bik="CURRENTBIK")
        payload = _valid_payload(supplier_iik="KZ1C00000000000001", supplier_bik="1C_BIK")

        cleaned = strip_tenant_sourced_fields(payload, tenant)

        assert cleaned["supplier_iik"] == "KZ1C00000000000001"
        assert cleaned["supplier_bik"] == "1C_BIK"

    def test_value_matching_tenant_fallback_is_stripped(self, db_session):
        """The complementary, pre-existing-intent case: if the payload's
        value is indistinguishable from what tenant-only fallback would
        produce, it really did come from the fallback (1C had nothing) —
        must still be stripped so an admin's later edit is picked up live."""
        tenant = make_tenant(db_session, invoice_iik="KZ999CURRENTACCOUNT", invoice_bank_bik="CURRENTBIK")
        payload = _valid_payload(supplier_iik="KZ999CURRENTACCOUNT", supplier_bik="CURRENTBIK")

        cleaned = strip_tenant_sourced_fields(payload, tenant)

        assert "supplier_iik" not in cleaned
        assert "supplier_bik" not in cleaned

    def test_empty_tenant_fallback_never_strips_a_present_1c_value(self, db_session):
        """The exact real-world shape post-migration f6a7b8c9d0e1: tenant
        fields are NULL, but this invoice's payload has real 1C-sourced
        bank data — must be kept, not discarded because it "matches" an
        empty fallback (it can't — empty never equals a real value)."""
        tenant = make_tenant(
            db_session, invoice_iik=None, invoice_bank_bik=None, invoice_bank_name=None, invoice_kbe=None
        )
        payload = _valid_payload(supplier_iik="KZ1C00000000000001", supplier_bik="1C_BIK")

        cleaned = strip_tenant_sourced_fields(payload, tenant)

        assert cleaned["supplier_iik"] == "KZ1C00000000000001"
        assert cleaned["supplier_bik"] == "1C_BIK"

    def test_nested_supplier_dict_is_never_stripped(self, db_session):
        """_merge_supplier_requisites never touches the nested "supplier"
        dict (only the flat supplier_* keys) — it can only ever be 1C-native
        content, so unlike the flat keys it's never a stripping candidate."""
        tenant = make_tenant(db_session, invoice_iik="KZ999CURRENTACCOUNT")
        payload = _valid_payload()

        cleaned = strip_tenant_sourced_fields(payload, tenant)

        assert cleaned["supplier"] == {"name": "1C Original Supplier", "iik": "KZ1C00000000000001"}

    def test_already_empty_field_is_left_alone(self, db_session):
        tenant = make_tenant(db_session, invoice_iik="KZ999CURRENTACCOUNT")
        payload = _valid_payload()
        payload.pop("supplier_iik")

        cleaned = strip_tenant_sourced_fields(payload, tenant)

        assert "supplier_iik" not in cleaned


class TestStorePayloadIfValid:
    def test_valid_payload_is_stored(self, db_session):
        """tenant=tenant (the real call shape every production caller uses)
        — this fixture's supplier_iik genuinely differs from the tenant's
        own fallback value, so it's 1C-native and correctly survives into
        the stored row (see TestStripTenantSourcedFields for the isolated
        version of this check)."""
        tenant = make_tenant(db_session)
        ok = store_payload_if_valid(
            db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova", tenant=tenant
        )
        assert ok is True
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _REAL_INVOICE_ID
        ).first()
        assert row is not None
        assert row.payload["number"] == "18490"
        assert row.payload["supplier_iik"] == "KZ1C00000000000001"

    def test_no_tenant_kwarg_falls_back_to_unconditional_strip(self, db_session):
        """Defensive default path (tenant=None) — kept for a hypothetical
        caller without a tenant object handy."""
        tenant = make_tenant(db_session)
        ok = store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova")
        assert ok is True
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _REAL_INVOICE_ID
        ).first()
        assert "supplier_iik" not in row.payload

    def test_invalid_payload_is_rejected_not_stored(self, db_session):
        tenant = make_tenant(db_session)
        ok = store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, {"number": "18490"}, source="nova")
        assert ok is False
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _REAL_INVOICE_ID
        ).first()
        assert row is None

    def test_failed_rehydrate_does_not_clobber_existing_valid_cache(self, db_session):
        """The exact scenario the user raised: 'what if we think rehydrate
        succeeded but it came back done [i.e. degraded]?' — never
        delete-then-write, same principle as xlsx_import/upsert.py."""
        tenant = make_tenant(db_session)
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova")

        ok = store_payload_if_valid(
            db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(items=[]), source="nova"
        )

        assert ok is False
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _REAL_INVOICE_ID
        ).first()
        assert row.payload["items"]  # original valid payload untouched

    def test_reject_non_guid_invoice_id(self, db_session):
        tenant = make_tenant(db_session)
        with pytest.raises(ValidationError):
            store_payload_if_valid(db_session, tenant.id, "'; DROP TABLE invoice_pdf_payloads; --", _valid_payload(), source="nova")


class TestGetCachedPayload:
    def test_no_cache_returns_none(self, db_session):
        tenant = make_tenant(db_session)
        assert get_cached_payload(db_session, tenant, _REAL_INVOICE_ID) is None

    def test_1c_native_bank_data_survives_a_cache_round_trip(self, db_session):
        """The 2026-09-01 bug fix, end-to-end: a payload whose supplier_iik
        genuinely came from 1C (here, deliberately different from the
        tenant's own fallback) must still be there on the NEXT read — not
        silently dropped and replaced by the tenant's unrelated fallback
        value. This is what the real Nova/OData live paths hand to
        store_payload_if_valid (see nova_buh_1c_client.py/odata_1c_client.py)."""
        tenant = make_tenant(db_session, invoice_iik="KZ999CURRENTACCOUNT", invoice_bank_bik="CURRENTBIK")
        payload = _valid_payload(supplier_iik="KZ1C00000000000001", supplier_bik="1C_BIK")
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, payload, source="nova", tenant=tenant)

        result = get_cached_payload(db_session, tenant, _REAL_INVOICE_ID)

        assert result["supplier_iik"] == "KZ1C00000000000001"
        assert result["supplier_bik"] == "1C_BIK"
        assert result["number"] == "18490"

    def test_1c_native_bank_data_survives_even_when_tenant_fields_are_empty(self, db_session):
        """The exact real-world shape of the bug: post-migration
        f6a7b8c9d0e1, every real tenant's invoice_iik/etc are NULL. Before
        this fix, the cache would strip the 1C-sourced bank data
        unconditionally and the SECOND view of this exact invoice would
        either raise MissingSupplierRequisitesError (Nova) or silently
        render with blank banks (OData) — even though the first view, and
        a fresh live re-fetch, would both succeed with real data."""
        tenant = make_tenant(
            db_session, invoice_iik=None, invoice_bank_bik=None, invoice_bank_name=None, invoice_kbe=None
        )
        payload = _valid_payload(supplier_iik="KZ1C00000000000001", supplier_bik="1C_BIK")
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, payload, source="nova", tenant=tenant)

        result = get_cached_payload(db_session, tenant, _REAL_INVOICE_ID)

        assert result["supplier_iik"] == "KZ1C00000000000001"
        assert result["supplier_bik"] == "1C_BIK"

    def test_tenant_requisites_change_reflected_immediately_no_cache_invalidation_needed(self, db_session):
        """The complementary, still-preserved guarantee: when 1C itself had
        nothing for this field (payload never carries it at write time —
        the realistic shape when only tenant fallback fills the gap), an
        admin correcting the tenant's bank account must apply to
        already-cached invoices with zero extra action."""
        tenant = make_tenant(db_session, invoice_iik="KZ999CURRENTACCOUNT", invoice_bank_bik="CURRENTBIK")
        payload = _valid_payload()
        payload.pop("supplier_iik")
        payload.pop("supplier_bik")
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, payload, source="nova", tenant=tenant)

        tenant.invoice_iik = "KZ777NEWACCOUNTAFTERCORRECTION"
        db_session.commit()

        result = get_cached_payload(db_session, tenant, _REAL_INVOICE_ID)
        assert result["supplier_iik"] == "KZ777NEWACCOUNTAFTERCORRECTION"

    def test_force_refresh_placeholder_row_not_returned_as_cache_hit(self, db_session):
        """A row can exist purely for force-refresh throttling (payload
        NULL, see mark_force_refresh_attempted) — must never be mistaken
        for a real cache hit."""
        tenant = make_tenant(db_session)
        mark_force_refresh_attempted(db_session, tenant.id, _REAL_INVOICE_ID)

        assert get_cached_payload(db_session, tenant, _REAL_INVOICE_ID) is None


class TestLineItemsFreshnessTtl:
    """Real bug found 2026-09-14 (Astranium/"Toys market" invoice
    №00000003340): line items (quantity/price/amount) had no TTL at all,
    unlike supplier requisites (always re-merged fresh per read, see
    TestStripTenantSourcedFields). A payload cached once at a moment when
    1C still had provisional figures (utilities like ТБО/теплоэнергия are
    often finalized later than electricity/water) stayed wrong forever —
    the invoice's total was off by ~1.09 KZT vs the live 1C document,
    with zero automatic path back to correct data short of a manual
    superadmin force-refresh."""

    def _age_the_cached_row(self, db_session, tenant, invoice_id, age: timedelta):
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == invoice_id
        ).first()
        row.fetched_at = datetime.now(timezone.utc) - age
        db_session.commit()

    def test_fresh_cache_within_ttl_is_still_served(self, db_session):
        tenant = make_tenant(db_session)
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova", tenant=tenant)
        self._age_the_cached_row(db_session, tenant, _REAL_INVOICE_ID, LINE_ITEMS_FRESHNESS_TTL - timedelta(minutes=1))

        result = get_cached_payload(db_session, tenant, _REAL_INVOICE_ID)

        assert result is not None
        assert result["number"] == "18490"

    def test_cache_older_than_ttl_is_treated_as_a_miss(self, db_session):
        """The actual fix: past the TTL, get_cached_payload must return
        None so the caller falls through to a live 1C re-fetch, exactly
        like a never-cached invoice — this is what closes the staleness
        window instead of freezing bad line items forever."""
        tenant = make_tenant(db_session)
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova", tenant=tenant)
        self._age_the_cached_row(db_session, tenant, _REAL_INVOICE_ID, LINE_ITEMS_FRESHNESS_TTL + timedelta(minutes=1))

        assert get_cached_payload(db_session, tenant, _REAL_INVOICE_ID) is None

    def test_is_payload_cache_stale_false_when_never_cached(self, db_session):
        """Distinguishes 'never cached' from 'cached but expired' — callers
        (Nova's file-level PDF cache guard) must NOT invalidate anything
        extra for an invoice that was simply never payload-cached."""
        tenant = make_tenant(db_session)
        assert is_payload_cache_stale(db_session, tenant.id, _REAL_INVOICE_ID) is False

    def test_is_payload_cache_stale_false_when_fresh(self, db_session):
        tenant = make_tenant(db_session)
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova", tenant=tenant)

        assert is_payload_cache_stale(db_session, tenant.id, _REAL_INVOICE_ID) is False

    def test_is_payload_cache_stale_true_past_ttl(self, db_session):
        tenant = make_tenant(db_session)
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova", tenant=tenant)
        self._age_the_cached_row(db_session, tenant, _REAL_INVOICE_ID, LINE_ITEMS_FRESHNESS_TTL + timedelta(minutes=1))

        assert is_payload_cache_stale(db_session, tenant.id, _REAL_INVOICE_ID) is True

    def test_is_payload_cache_stale_false_for_force_refresh_placeholder(self, db_session):
        """A throttle-only placeholder row (payload NULL, fetched_at NULL)
        must not be reported as 'stale' — there's no cached content to be
        stale in the first place, see _row_is_stale's fetched_at is None
        guard."""
        tenant = make_tenant(db_session)
        mark_force_refresh_attempted(db_session, tenant.id, _REAL_INVOICE_ID)

        assert is_payload_cache_stale(db_session, tenant.id, _REAL_INVOICE_ID) is False


class TestForceRefreshThrottle:
    def test_first_attempt_always_allowed(self, db_session):
        tenant = make_tenant(db_session)
        assert can_attempt_force_refresh(db_session, tenant.id, _REAL_INVOICE_ID) is True

    def test_immediate_second_attempt_blocked(self, db_session):
        tenant = make_tenant(db_session)
        mark_force_refresh_attempted(db_session, tenant.id, _REAL_INVOICE_ID)
        assert can_attempt_force_refresh(db_session, tenant.id, _REAL_INVOICE_ID) is False

    def test_attempt_after_cooldown_allowed(self, db_session):
        tenant = make_tenant(db_session)
        mark_force_refresh_attempted(db_session, tenant.id, _REAL_INVOICE_ID)
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _REAL_INVOICE_ID
        ).first()
        row.last_force_refresh_attempt_at = datetime.now(timezone.utc) - FORCE_REFRESH_COOLDOWN - timedelta(seconds=1)
        db_session.commit()

        assert can_attempt_force_refresh(db_session, tenant.id, _REAL_INVOICE_ID) is True

    def test_throttle_applies_even_when_invoice_never_had_a_valid_payload(self, db_session):
        """The exact gap found during design: an invoice_id that never
        passes the validity gate must still be throttleable, or force=True
        spam against a permanently-broken invoice becomes an unthrottled
        way to keep hammering 1C."""
        tenant = make_tenant(db_session)
        mark_force_refresh_attempted(db_session, tenant.id, _REAL_INVOICE_ID)
        # Simulate rehydrate attempts that keep failing validity.
        store_payload_if_valid(db_session, tenant.id, _REAL_INVOICE_ID, {}, source="nova")

        assert can_attempt_force_refresh(db_session, tenant.id, _REAL_INVOICE_ID) is False

    def test_throttle_is_scoped_per_tenant_and_invoice(self, db_session):
        tenant_a = make_tenant(db_session, trc_name="TRC A", name="A", legal_name="A LLP")
        tenant_b = make_tenant(db_session, trc_name="TRC B", name="B", legal_name="B LLP")
        mark_force_refresh_attempted(db_session, tenant_a.id, _REAL_INVOICE_ID)

        assert can_attempt_force_refresh(db_session, tenant_a.id, _REAL_INVOICE_ID) is False
        assert can_attempt_force_refresh(db_session, tenant_b.id, _REAL_INVOICE_ID) is True
