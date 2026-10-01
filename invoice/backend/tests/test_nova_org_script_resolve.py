from app.services.nova_1c_service import Nova1CService
from app.services.nova_org_resolve import _script_fields_for_response


def test_find_script_id_normalizes_yo():
    scripts = [{"ID": 75, "name": "Счет по UID (+статус)"}]
    assert Nova1CService.find_script_id(scripts, "счёт по uid") == 75


def test_resolve_script_ids_per_org_moon_style():
    service = Nova1CService.__new__(Nova1CService)
    service.list_scripts = lambda _org_id: [  # type: ignore[method-assign]
        {"ID": 71, "name": "Счета (+Остаток/СтатусОплаты)"},
        {"ID": 72, "name": "Платежи (+chequeKKM)"},
        {"ID": 73, "name": "Контрагенты (+folderType/email/phone)"},
        {"ID": 74, "name": "Баланс/взаиморасчёты"},
        {"ID": 75, "name": "Счёт по UID (+статус)"},
        {"ID": 86, "name": "АВР по UID"},
    ]
    mapping = service.resolve_script_ids(127)
    assert mapping["invoices"] == 71
    assert mapping["payments"] == 72
    assert mapping["counterparties"] == 73
    assert mapping["balance"] == 74
    assert mapping["invoice_by_id"] == 75


def test_script_fields_prefer_resolved_over_defaults():
    fields = _script_fields_for_response(
        "odata",
        resolved={
            "invoices": 71,
            "payments": 72,
            "counterparties": 73,
            "balance": 74,
            "invoice_by_id": 75,
        },
    )
    assert fields == {
        "nova_script_invoices": 71,
        "nova_script_payments": 72,
        "nova_script_counterparties": 73,
        "nova_script_balance": 74,
        "nova_script_invoice_by_id": 75,
    }
