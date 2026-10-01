from app.services.nova_buh_1c_client import (
    _counterparty_rows_from_results,
    _enrich_counterparties_phones,
    _normalize_counterparty_row,
    _phones_by_counterparty_from_results,
)
from app.services.nova_query_results import query_step_to_dicts
from app.client_1c.models import Counterparty


def test_query_step_to_dicts_maps_phone_number_from_columns():
    step = {
        "columns": ["id", "fullName", "phoneNumber"],
        "items": [
            ["cp-1", "Tenant A", "+77001112233"],
            ["cp-2", "Tenant B", ""],
        ],
    }
    rows = query_step_to_dicts(step)
    assert rows[0]["phoneNumber"] == "+77001112233"
    assert rows[1]["phoneNumber"] == ""


def test_counterparty_rows_from_results_com_query_step():
    results = {
        "counterparties": {
            "columns": ["id", "fullName", "bin", "phoneNumber"],
            "items": [
                ["guid-1", "Shop One", "123456789012", "+77001234567"],
            ],
        }
    }
    rows = _counterparty_rows_from_results(results)
    assert len(rows) == 1
    assert rows[0]["phoneNumber"] == "+77001234567"
    assert rows[0]["fullName"] == "Shop One"


def test_normalize_counterparty_row_cyrillic_phone_key():
    row = {"id": "x", "fullName": "Test", "Телефон": "+77009998877"}
    out = _normalize_counterparty_row(row)
    assert out["phoneNumber"] == "+77009998877"


def test_phones_from_contact_info_batch():
    cp_id = "80da8377-6200-11f0-8454-bca8a681a811"
    results = {
        "counterparties": {
            "columns": ["id", "fullName", "bin", "phoneNumber"],
            "items": [[cp_id, "ACCENT ИП", "123456789012", ""]],
        },
        "batch": {
            "batch": [
                {
                    "columns": ["Объект", "Тип", "Представление"],
                    "items": [
                        [cp_id, "Телефон", "+7 (701) 123-45-67"],
                    ],
                }
            ]
        },
    }
    phones = _phones_by_counterparty_from_results(results)
    assert phones[cp_id] == "+77011234567"


def test_enrich_counterparties_phones_fills_empty():
    cp_id = "guid-1"
    results = {
        "counterparties": {
            "columns": ["id", "fullName", "phoneNumber"],
            "items": [[cp_id, "Shop", ""]],
        },
        "contacts": {
            "columns": ["Объект", "Представление"],
            "items": [[cp_id, "+77005556677"]],
        },
    }
    rows = _counterparty_rows_from_results(results)
    phones = _phones_by_counterparty_from_results(results)
    cps = [Counterparty.from_dict(r) for r in rows]
    _enrich_counterparties_phones(cps, phones)
    assert cps[0].phone_number == "+77005556677"
