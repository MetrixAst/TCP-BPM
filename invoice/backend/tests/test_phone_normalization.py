"""normalize_phone used to treat "8707..." (the everyday domestic way KZ/RU
mobile numbers are written/dialed) as a distinct string from "+7707..."/
"7707...", even though they're the same phone number. See audit from
2026-08-25: this could make assert_phone_allowed_for_counterparty wrongly
reject a legitimate WhatsApp recipient, or split one real phone into two
"different" entries in dedup logic."""

from app.services.phone_list import normalize_phone, normalized_phone_set


def test_leading_8_and_leading_7_normalize_to_same_value():
    assert normalize_phone("87071234567") == normalize_phone("+77071234567")
    assert normalize_phone("87071234567") == "77071234567"


def test_leading_8_with_formatting_normalizes():
    assert normalize_phone("8 (707) 123-45-67") == "77071234567"


def test_ten_digit_number_gets_country_code():
    assert normalize_phone("7071234567") == "77071234567"


def test_plus7_and_bare_7_are_equal():
    assert normalize_phone("+77071234567") == normalize_phone("77071234567")


def test_normalized_phone_set_dedupes_8_and_7_variants():
    result = normalized_phone_set("87071234567;+77071234567")
    assert result == {"77071234567"}


def test_empty_and_garbage_input():
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""
