"""Tests for counterparty name matching."""

from app.services.counterparty_name_match import (
    VIRTUAL_PREFIX,
    build_name_resolution_index,
    is_virtual_counterparty_id,
    resolve_payment_counterparty_key,
    resolve_to_cache_counterparty_id,
    virtual_counterparty_key,
)


def test_build_name_resolution_index_unambiguous():
    cache = [
        {"id": "AAA", "fullName": "Сахариева ИП (Фудкорд)"},
        {"id": "BBB", "fullName": "Бексултан ИП (KhanBurger)"},
    ]
    index = build_name_resolution_index(cache)
    assert index["сахариева ип (фудкорд)"] == "aaa"
    assert index["сахариева ип"] == "aaa"
    assert resolve_to_cache_counterparty_id("Сахариева ИП (Фудкорд)", index) == "aaa"


def test_ambiguous_name_not_resolved():
    cache = [
        {"id": "AAA", "fullName": "Иванов ИП"},
        {"id": "BBB", "fullName": "Иванов ИП (магазин)"},
    ]
    index = build_name_resolution_index(cache)
    assert resolve_to_cache_counterparty_id("Иванов ИП (другой)", index) is None


def test_virtual_key_for_unknown_name():
    key, name = resolve_payment_counterparty_key(
        counterparty_id="",
        tenant_name="Неизвестный Арендатор ИП",
        name_index={},
    )
    assert key.startswith(VIRTUAL_PREFIX)
    assert name == "Неизвестный Арендатор ИП"
    assert is_virtual_counterparty_id(key)
    assert virtual_counterparty_key("Неизвестный Арендатор ИП") == key


def test_existing_counterparty_id_preserved():
    key, name = resolve_payment_counterparty_key(
        counterparty_id="Real-UUID",
        tenant_name="",
        name_index={},
        cache_names_by_id={"real-uuid": "Полное имя"},
    )
    assert key == "real-uuid"
    assert name == "Полное имя"
