"""NovaBuh1CClient.get_invoice_counterparty_id — real incident 2026-08-31:
Maxi Mall's Nova org (119) had its 1C credentials broken (every script call
failed with 'Неверный логин или пароль пользователя 1С', confirmed by
running every registered script directly). This function used to swallow
that exact error into a bare None on both of its two lookup attempts —
which assert_invoice_belongs_to_counterparty then reported upstream as a
plain 404 'Счёт не найден в 1С' (and, before an earlier fix this same
session, as a flat-out misleading 500). Neither told anyone the real
problem was a broken 1C login, not a missing invoice.

Must still try both lookup strategies even after the first fails — see
nova_1c_scripts_audit: different Nova orgs return different response
shapes, so the second strategy is a legitimate fallback for 'this script
isn't configured for this org', not just a retry of the same failure."""
from unittest.mock import MagicMock

import pytest

from app.services.nova_1c_service import Nova1CServiceError
from app.services.nova_buh_1c_client import NovaBuh1CClient

_INVOICE_ID = "a57d2d95-8675-11f1-b51e-4c526260eadc"
_LOGIN_ERROR = "Неверный логин или пароль пользователя 1С."


def _client() -> NovaBuh1CClient:
    return NovaBuh1CClient(organization_id=119, service=MagicMock())


class TestGetInvoiceCounterpartyId:
    def test_both_strategies_failing_raises_instead_of_returning_none(self):
        """The core regression: a real 1C connectivity/auth failure must
        surface as an exception (-> 503 upstream), not silently become
        'not found' (-> misleading 404)."""
        client = _client()
        client._run = MagicMock(side_effect=Nova1CServiceError(_LOGIN_ERROR))
        client._ensure_invoice_index = MagicMock(side_effect=Nova1CServiceError(_LOGIN_ERROR))

        with pytest.raises(Nova1CServiceError, match=_LOGIN_ERROR):
            client.get_invoice_counterparty_id(_INVOICE_ID)

    def test_first_strategy_fails_second_succeeds_returns_id_not_error(self):
        """Legitimate fallback case must still work — a script simply not
        registered for this org (or a different response shape) is not the
        same as the whole connection being broken."""
        client = _client()
        client._run = MagicMock(side_effect=Nova1CServiceError("script «invoice_by_id» not found"))

        def fake_ensure_index():
            client._invoice_headers_by_id = {_INVOICE_ID: {"counterparty_id": "cp-123"}}

        client._ensure_invoice_index = MagicMock(side_effect=fake_ensure_index)

        result = client.get_invoice_counterparty_id(_INVOICE_ID)

        assert result == "cp-123"

    def test_both_strategies_succeed_but_find_nothing_returns_none(self):
        """Genuine 'this invoice really doesn't exist' case — no exception
        anywhere, both lookups just come back empty. Must still return
        None, not raise anything."""
        client = _client()
        client._run = MagicMock(return_value={"result": {"results": {}}})
        client._ensure_invoice_index = MagicMock()  # populates nothing

        result = client.get_invoice_counterparty_id(_INVOICE_ID)

        assert result is None
        client._run.assert_called_once()
        client._ensure_invoice_index.assert_called_once()

    def test_in_memory_cache_hit_skips_both_live_lookups(self):
        client = _client()
        client._invoice_headers_by_id = {_INVOICE_ID: {"counterparty_id": "cp-cached"}}
        client._run = MagicMock(side_effect=AssertionError("must not be called on a cache hit"))
        client._ensure_invoice_index = MagicMock(side_effect=AssertionError("must not be called on a cache hit"))

        result = client.get_invoice_counterparty_id(_INVOICE_ID)

        assert result == "cp-cached"

    def test_first_strategy_succeeds_returns_immediately_without_second(self):
        client = _client()
        client._run = MagicMock(
            return_value={
                "result": {"results": {"invoice": {"counterparty_id": "cp-from-first-call"}}}
            }
        )
        client._ensure_invoice_index = MagicMock(side_effect=AssertionError("must not be called"))

        result = client.get_invoice_counterparty_id(_INVOICE_ID)

        assert result == "cp-from-first-call"
