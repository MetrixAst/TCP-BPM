"""NovaBuh1CClient.download_invoice_file — wiring of the structured-payload
cache (app/services/invoice_pdf_cache.py) short-circuits the live 1C
cascade entirely on a cache hit. Can't verify this against real Nova data
locally (this env's test tenant's COM/PDF-specific credentials don't
authenticate at all — 'Неверный логин или пароль пользователя 1С', a
pre-existing environment limitation, not something this change touches),
so this proves the control flow directly instead: on a cache hit, none of
the live-fetch entry points (_ensure_agent_id, _ensure_scripts, _run,
_lookup_batch_invoice) may be called at all."""
from unittest.mock import MagicMock, patch

import pytest

from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.services.nova_buh_1c_client import NovaBuh1CClient


def _client() -> NovaBuh1CClient:
    return NovaBuh1CClient(organization_id=999, service=MagicMock())


def _fake_tenant():
    tenant = MagicMock()
    tenant.id = 42
    tenant.legal_name = "Cache Wiring Test Tenant"
    tenant.name = "Cache Wiring Test Tenant"
    return tenant


def _valid_cached_payload() -> dict:
    return {
        "id": "f49e3940-9563-11f1-b522-4c526260eadb",
        "number": "18490",
        "date": "2026-08-01",
        "counterparty_id": "f49e393a-9563-11f1-b522-4c526260eadb",
        "counterparty_name": "Renter TOO",
        "amount": 500000,
        "items": [{"name": "Аренда", "quantity": 1, "price": 500000, "amount": 500000}],
        # These are what get_cached_payload would have already merged in
        # from the tenant — present here since we're stubbing that function
        # directly, not exercising its real merge logic (covered by
        # tests/test_invoice_pdf_cache.py already).
        "supplier_iik": "KZ999CURRENTACCOUNT",
        "supplier_bik": "CURRENTBIK",
    }


def _forbid(name):
    return MagicMock(side_effect=AssertionError(f"{name} must not be called on a cache hit"))


class TestCacheHitSkipsLiveCascade:
    def test_cache_hit_never_touches_any_live_1c_entry_point(self, tmp_path):
        client = _client()
        # Every method that would talk to Nova if reached.
        client._ensure_agent_id = _forbid("_ensure_agent_id")
        client._ensure_scripts = _forbid("_ensure_scripts")
        client._run = _forbid("_run")
        client._lookup_batch_invoice = _forbid("_lookup_batch_invoice")
        client._enrich_com_pdf_payload = _forbid("_enrich_com_pdf_payload")

        out_pdf = tmp_path / "invoice.pdf"

        with patch(
            "app.services.invoice_pdf_cache.get_cached_payload",
            return_value=_valid_cached_payload(),
        ), patch(
            "app.services.invoice_report.generate_formal_invoice_document",
            return_value=str(out_pdf),
        ):
            out_pdf.write_bytes(b"%PDF-1.4 fake")
            result = client.download_invoice_file(
                "f49e3940-9563-11f1-b522-4c526260eadb",
                save_path=str(out_pdf),
                tenant=_fake_tenant(),
            )

        assert result == str(out_pdf.resolve())

    def test_cache_hit_without_supplier_banks_raises_same_error_as_live_path(self, tmp_path):
        """Behavioral parity with the cache-miss path: a payload missing
        supplier requisites must still raise MissingSupplierRequisitesError,
        not silently render a bank-less PDF."""
        client = _client()
        client._ensure_agent_id = _forbid("_ensure_agent_id")

        payload = _valid_cached_payload()
        payload.pop("supplier_iik")
        payload.pop("supplier_bik")

        with patch("app.services.invoice_pdf_cache.get_cached_payload", return_value=payload):
            with pytest.raises(MissingSupplierRequisitesError):
                client.download_invoice_file(
                    "f49e3940-9563-11f1-b522-4c526260eadb",
                    save_path=str(tmp_path / "invoice.pdf"),
                    tenant=_fake_tenant(),
                )

    def test_force_true_bypasses_cache_read(self, tmp_path):
        """force=True must skip the cache lookup — proven by never even
        calling get_cached_payload, not just by it returning something
        different."""
        client = _client()
        client._ensure_agent_id = MagicMock()  # allowed to be reached now
        client._ensure_scripts = MagicMock()

        with patch("app.services.invoice_pdf_cache.get_cached_payload") as mock_get:
            try:
                client.download_invoice_file(
                    "f49e3940-9563-11f1-b522-4c526260eadb",
                    save_path=str(tmp_path / "invoice.pdf"),
                    tenant=_fake_tenant(),
                    force=True,
                )
            except Exception:
                pass  # the live cascade will fail against mocks — irrelevant here
            mock_get.assert_not_called()

    def test_no_tenant_resolved_skips_cache_entirely_falls_through_to_live_path(self, tmp_path):
        """tenant=None (unresolvable) — get_cached_payload needs a tenant to
        merge requisites from, so the cache is skipped, not crashed on."""
        client = _client()
        client._ensure_agent_id = MagicMock()

        with patch("app.services.invoice_pdf_cache.get_cached_payload") as mock_get:
            try:
                client.download_invoice_file(
                    "f49e3940-9563-11f1-b522-4c526260eadb",
                    save_path=str(tmp_path / "invoice.pdf"),
                    tenant=None,
                )
            except Exception:
                pass
            mock_get.assert_not_called()
