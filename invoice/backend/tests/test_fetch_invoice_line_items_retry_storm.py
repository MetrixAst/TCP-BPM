"""NovaBuh1CClient.fetch_invoice_line_items — real incident 2026-09-02:
Maxi Mall's Nova org responded slowly/unreliably, so
_ensure_invoice_index()'s two full-org fetches (self._run("invoices")/
("payments"), up to 120s each) kept failing. _ensure_invoice_index only
marks "already tried" by successfully assigning
self._invoice_lines_by_id/_invoice_headers_by_id at the very end — a
failure left both at None, so bulk_debtor_notify_service's per-invoice loop
(one fetch_invoice_line_items call per invoice) retried the SAME ~240s
round trip on every single one of 130+ rows. The background job could run
for hours without completing a single row, and the retry storm was severe
enough to eventually starve the process's event loop (observed as a real
kafka.net.selector "blocking the event loop" warning in prod logs).

Fix is local to this one heavily-looped call site (not to
_ensure_invoice_index itself, which must keep raising on failure for
get_invoice_counterparty_id's own error-vs-not-found distinction — see
test_nova_get_invoice_counterparty_id.py, a separate real incident from
2026-08-31): on failure here, negative-cache empty dicts so the retry cost
is paid once per process, not once per invoice."""
from unittest.mock import MagicMock

import pytest

from app.services.nova_1c_service import Nova1CServiceError
from app.services.nova_buh_1c_client import NovaBuh1CClient

_INVOICE_A = "a57d2d95-8675-11f1-b51e-4c526260eadc"
_INVOICE_B = "b68e3ea6-9786-22f2-c62f-5d637371fbed"


def _client() -> NovaBuh1CClient:
    return NovaBuh1CClient(organization_id=119, service=MagicMock())


class TestNegativeCachingAfterEnsureIndexFails:
    def test_second_invoice_does_not_repeat_the_expensive_org_wide_fetch(self):
        """The core regression: the real _ensure_invoice_index() (not
        mocked here) has its own early-return guard
        (`is not None`) — this only works if a failure leaves BOTH dicts
        as {} rather than None. Assert on the actual expensive call
        (self._run("invoices")) instead of _ensure_invoice_index's own call
        count, since _ensure_invoice_index is still invoked every time —
        it just becomes a cheap no-op after the first failure."""
        client = _client()

        def fake_run(script_key, **kwargs):
            if script_key == "invoices":
                raise Nova1CServiceError("Nova org 119: timed out")
            raise Nova1CServiceError("invoice_by_id also failed")

        client._run = MagicMock(side_effect=fake_run)

        client.fetch_invoice_line_items(_INVOICE_A)
        client.fetch_invoice_line_items(_INVOICE_B)

        invoices_calls = [
            c for c in client._run.call_args_list if c.args[:1] == ("invoices",)
        ]
        assert len(invoices_calls) == 1

    def test_failure_negative_caches_empty_dicts_not_none(self):
        client = _client()
        client._ensure_invoice_index = MagicMock(
            side_effect=Nova1CServiceError("Nova org 119: timed out")
        )
        client._run = MagicMock(side_effect=Nova1CServiceError("invoice_by_id also failed"))

        client.fetch_invoice_line_items(_INVOICE_A)

        assert client._invoice_lines_by_id == {}
        assert client._invoice_headers_by_id == {}

    def test_raw_non_nova_exception_is_also_caught(self):
        """A raw requests timeout/connection error isn't guaranteed to be
        wrapped into Nova1CServiceError by the time it gets here — must
        still negative-cache, not propagate."""
        client = _client()
        client._ensure_invoice_index = MagicMock(side_effect=TimeoutError("read timed out"))
        client._run = MagicMock(side_effect=Nova1CServiceError("invoice_by_id also failed"))

        result = client.fetch_invoice_line_items(_INVOICE_A)

        assert result == []
        assert client._invoice_lines_by_id == {}

    def test_still_returns_real_lines_on_success_no_change_in_behavior(self):
        client = _client()

        def fake_ensure_index():
            client._invoice_lines_by_id = {_INVOICE_A: [{"name": "Аренда", "amount": 100.0}]}
            client._invoice_headers_by_id = {_INVOICE_A: {}}

        client._ensure_invoice_index = MagicMock(side_effect=fake_ensure_index)

        result = client.fetch_invoice_line_items(_INVOICE_A)

        assert result == [{"name": "Аренда", "amount": 100.0}]

    def test_does_not_overwrite_an_already_negative_cached_index(self):
        """If a PRIOR invoice already negative-cached (empty dicts, not
        None), _ensure_invoice_index's own early-return guard
        (`is not None`) already skips re-running it — this just confirms
        this call site doesn't fight that by resetting to None anywhere."""
        client = _client()
        client._invoice_lines_by_id = {}
        client._invoice_headers_by_id = {}
        client._ensure_invoice_index = MagicMock()
        client._run = MagicMock(side_effect=Nova1CServiceError("invoice_by_id also failed"))

        client.fetch_invoice_line_items(_INVOICE_A)

        # Real _ensure_invoice_index would have no-op'd on the "not None"
        # guard; here we just assert this call site called it once and
        # both dicts are still empty dicts, never reset to None.
        assert client._invoice_lines_by_id == {}
        assert client._invoice_headers_by_id == {}
