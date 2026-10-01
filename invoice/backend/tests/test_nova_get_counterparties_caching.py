"""NovaBuh1CClient.get_counterparties — real incident 2026-09-02: the bulk
debtor mailing's phone fallback (get_1c_phones_for_counterparty in
invoice_access.py) calls this with limit=50000 for EVERY counterparty that
has no admin-entered phone, just to find that one counterparty's own
number. With no caching, the WHOLE org's counterparty list (a live, full
1C fetch — ~545 rows for Maxi Mall) got re-fetched from scratch on every
one of 200+ rows in a single bulk run — the same retry-storm shape as the
earlier _ensure_invoice_index fix today, just hiding in a different
function that fix didn't touch."""
from unittest.mock import MagicMock

from app.services.nova_buh_1c_client import NovaBuh1CClient


def _client() -> NovaBuh1CClient:
    return NovaBuh1CClient(organization_id=119, service=MagicMock())


def _counterparties_payload(rows):
    return {
        "result": {
            "results": {
                "counterparties": {"items": rows},
            }
        }
    }


class TestGetCounterpartiesCaching:
    def test_second_call_does_not_repeat_the_live_fetch(self):
        client = _client()
        client._run = MagicMock(
            return_value=_counterparties_payload(
                [{"id": "cp-1", "fullName": "ACME LLP", "phone": "+77001234567"}]
            )
        )

        client.get_counterparties(limit=50000)
        client.get_counterparties(limit=50000)

        counterparties_calls = [
            c for c in client._run.call_args_list if c.args[:1] == ("counterparties",)
        ]
        assert len(counterparties_calls) == 1

    def test_cached_result_is_still_correct_on_repeat_calls(self):
        client = _client()
        client._run = MagicMock(
            return_value=_counterparties_payload(
                [{"id": "cp-1", "fullName": "ACME LLP", "phone": "+77001234567"}]
            )
        )

        first = client.get_counterparties(limit=50000)
        second = client.get_counterparties(limit=50000)

        assert len(first) == len(second) == 1
        assert first[0].id == second[0].id == "cp-1"

    def test_smaller_limit_on_a_later_call_correctly_slices_the_cache(self):
        client = _client()
        client._run = MagicMock(
            return_value=_counterparties_payload(
                [
                    {"id": "cp-1", "fullName": "A"},
                    {"id": "cp-2", "fullName": "B"},
                    {"id": "cp-3", "fullName": "C"},
                ]
            )
        )

        client.get_counterparties(limit=50000)
        limited = client.get_counterparties(limit=2)

        assert len(limited) == 2
        # Still only one real fetch happened for either call.
        counterparties_calls = [
            c for c in client._run.call_args_list if c.args[:1] == ("counterparties",)
        ]
        assert len(counterparties_calls) == 1
