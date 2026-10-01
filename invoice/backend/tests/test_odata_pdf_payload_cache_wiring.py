"""OData1CClient.download_invoice_file — wiring of the structured-payload
cache. This path had NO cache of any kind before (see the removed comment
in odata_1c_client.py: 'OData-путь всегда перегенерирует файл, своего кэша
нет') — every view of every OData invoice hit live 1C unconditionally.
This proves the new cache-hit short-circuit actually skips
_build_invoice_pdf_payload (the thing that made every one of those live
OData calls) entirely."""
from unittest.mock import MagicMock, patch

from app.services.odata_1c_client import OData1CClient

_INVOICE_ID = "f49e3940-9563-11f1-b522-4c526260eadb"


def _client() -> OData1CClient:
    # __init__ unconditionally probes the server (_connect_with_retries) —
    # not relevant to what these tests check, and there's nothing real to
    # connect to here.
    with patch.object(OData1CClient, "_connect_with_retries"):
        client = OData1CClient(base_url="https://example.test/odata", api_user="u", api_password="p")
    client._access_token = "odata-basic"
    return client


def _fake_tenant():
    tenant = MagicMock()
    tenant.id = 42
    tenant.legal_name = "OData Cache Wiring Test Tenant"
    tenant.name = "OData Cache Wiring Test Tenant"
    return tenant


def _valid_cached_payload() -> dict:
    return {
        "id": _INVOICE_ID,
        "number": "18490",
        "date": "2026-08-01",
        "counterparty_id": "f49e393a-9563-11f1-b522-4c526260eadb",
        "counterparty_name": "Renter TOO",
        "amount": 500000,
        "items": [{"name": "Аренда", "quantity": 1, "price": 500000, "amount": 500000}],
        "supplier_iik": "KZ999CURRENTACCOUNT",
        "supplier_bik": "CURRENTBIK",
    }


class TestCacheHitSkipsLiveOData:
    def test_cache_hit_never_calls_build_invoice_pdf_payload(self, tmp_path):
        client = _client()
        client._build_invoice_pdf_payload = MagicMock(
            side_effect=AssertionError("_build_invoice_pdf_payload must not be called on a cache hit")
        )

        out_pdf = tmp_path / "invoice.pdf"
        out_pdf.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "app.services.invoice_pdf_cache.get_cached_payload",
            return_value=_valid_cached_payload(),
        ), patch(
            "app.services.invoice_report.generate_formal_invoice_document",
            return_value=str(out_pdf),
        ):
            result = client.download_invoice_file(
                _INVOICE_ID, save_path=str(out_pdf), tenant=_fake_tenant()
            )

        assert result == str(out_pdf)

    def test_force_true_bypasses_cache_read(self, tmp_path):
        client = _client()
        client._build_invoice_pdf_payload = MagicMock(return_value=None)

        with patch("app.services.invoice_pdf_cache.get_cached_payload") as mock_get:
            client.download_invoice_file(
                _INVOICE_ID, save_path=str(tmp_path / "invoice.pdf"), tenant=_fake_tenant(), force=True
            )
            mock_get.assert_not_called()

    def test_cache_miss_falls_through_and_stores_result(self, tmp_path):
        """The other half of the contract: a miss must still store whatever
        the live fetch produced, going forward the next call is a hit."""
        client = _client()
        fresh_payload = _valid_cached_payload()
        client._build_invoice_pdf_payload = MagicMock(return_value=fresh_payload)

        out_pdf = tmp_path / "invoice.pdf"

        with patch("app.services.invoice_pdf_cache.get_cached_payload", return_value=None), patch(
            "app.services.invoice_pdf_cache.store_payload_if_valid"
        ) as mock_store, patch(
            "app.services.invoice_report.generate_formal_invoice_document",
            return_value=str(out_pdf),
        ):
            out_pdf.write_bytes(b"%PDF-1.4 fake")
            client.download_invoice_file(_INVOICE_ID, save_path=str(out_pdf), tenant=_fake_tenant())

        mock_store.assert_called_once()
        args, kwargs = mock_store.call_args
        assert args[1] == 42  # tenant_id
        assert args[2] == _INVOICE_ID
        assert kwargs.get("source") == "odata" or (len(args) > 4 and args[4] == "odata")
