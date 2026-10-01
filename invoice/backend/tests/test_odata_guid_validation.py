"""OData resource paths used to be built by raw f-string interpolation of
externally-supplied invoice/counterparty ids (e.g. invoice_id straight from a
public download endpoint's path param) with no format check — a crafted value
could break out of the quoted `guid'...'` literal and reach the tenant's live
1C server verbatim. See audit from 2026-08-25.

These tests exercise the guard functions directly, plus the client methods
that are reachable with raw external input, without needing a live 1C
connection: none of the invalid-input branches below touch `self`, so calling
the unbound method with `self=None` is safe (mirrors the existing pattern in
test_payment_analytics_regressions.py)."""

import pytest

from app.client_1c.exceptions import ValidationError
from app.services.odata_1c_client import OData1CClient, _guid_literal, _looks_like_guid
from app.services.safe_filename import safe_filename_component

VALID_GUID = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
INJECTION_ATTEMPTS = [
    "x') or (1 eq 1) or Ref_Key eq guid'x",
    "../../etc/passwd",
    "'; DROP everything --",
    "",
    "   ",
    "not-a-guid-at-all",
]


def test_looks_like_guid_accepts_real_guid():
    assert _looks_like_guid(VALID_GUID)


@pytest.mark.parametrize("bad", INJECTION_ATTEMPTS)
def test_guid_literal_rejects_non_guid_input(bad):
    with pytest.raises(ValidationError):
        _guid_literal(bad, "invoice_id")


def test_guid_literal_accepts_and_lowercases_valid_guid():
    assert _guid_literal(VALID_GUID.upper(), "invoice_id") == VALID_GUID


@pytest.mark.parametrize("bad", INJECTION_ATTEMPTS)
def test_get_invoice_counterparty_id_returns_none_for_bad_id(bad):
    assert OData1CClient.get_invoice_counterparty_id(None, bad) is None


@pytest.mark.parametrize("bad", INJECTION_ATTEMPTS)
def test_fetch_invoice_line_items_returns_empty_for_bad_id(bad):
    assert OData1CClient.fetch_invoice_line_items(None, bad) == []


@pytest.mark.parametrize("bad", INJECTION_ATTEMPTS)
def test_build_invoice_pdf_payload_raises_for_bad_id(bad):
    with pytest.raises(ValidationError):
        OData1CClient._build_invoice_pdf_payload(None, bad)


@pytest.mark.parametrize("bad", INJECTION_ATTEMPTS)
def test_download_invoice_file_raises_for_bad_id(bad):
    with pytest.raises(ValidationError):
        OData1CClient.download_invoice_file(None, bad)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (VALID_GUID, VALID_GUID),
        ("../../etc/passwd", ".._.._etc_passwd"),
        ("x'); DROP TABLE--", "x____DROP_TABLE--"),
        ("", ""),
    ],
)
def test_safe_filename_component_strips_path_and_shell_metacharacters(raw, expected):
    result = safe_filename_component(raw)
    assert "/" not in result
    assert "\\" not in result
    assert result == expected
