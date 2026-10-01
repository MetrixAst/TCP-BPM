from app.services.nova_buh_1c_client import (
    _is_empty_guid,
    _parent_rows_from_results,
    _group_rows_from_results,
)
from app.client_1c.models import Counterparty


def test_is_empty_guid():
    assert _is_empty_guid("")
    assert _is_empty_guid("00000000-0000-0000-0000-000000000000")
    assert not _is_empty_guid("01fe6d73-58fb-11f1-91b1-0007432d89c8")


def test_parent_rows_from_results():
    rows = _parent_rows_from_results(
        {
            "counterparty_parents": {
                "columns": ["id", "parent", "folderName"],
                "items": [
                    ["aaa", "bbb", "Арендаторы"],
                ],
            }
        }
    )
    assert len(rows) == 1
    assert rows[0]["folderName"] == "Арендаторы"


def test_group_rows_from_results():
    rows = _group_rows_from_results(
        {
            "counterparty_groups": {
                "items": [
                    {"id": "1", "fullName": "Арендаторы", "parent": "00000000-0000-0000-0000-000000000000"},
                ]
            }
        }
    )
    assert rows[0]["fullName"] == "Арендаторы"


def test_counterparty_from_dict_folder_fields():
    cp = Counterparty.from_dict(
        {
            "id": "x",
            "fullName": "Shop",
            "parent": "folder-id",
            "folderName": "Арендаторы",
        }
    )
    assert cp.parent == "folder-id"
    assert cp.folder_name == "Арендаторы"
