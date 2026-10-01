from types import SimpleNamespace

from app.client_1c.models import Counterparty
from app.services.counterparty_folder_enrichment import (
    enrich_counterparties_with_folders,
    folders_payload_from_counterparties,
)


def test_folders_payload_from_counterparties():
    cps = [
        Counterparty(id="1", full_name="A", parent="p1", folder_name="Арендаторы"),
        Counterparty(id="2", full_name="B", parent="p1", folder_name="Арендаторы"),
        Counterparty(id="3", full_name="C", parent="p2", folder_name="ГПХ"),
    ]
    folders = folders_payload_from_counterparties(cps)
    assert [f["fullName"] for f in folders] == ["Арендаторы", "ГПХ"]


def test_enrich_uses_existing_parent_and_groups():
    cps = [
        Counterparty(id="aaa", full_name="Shop", parent="folder-1", folder_name=""),
    ]

    class FakeNova:
        def get_counterparty_groups(self):
            return [{"id": "folder-1", "fullName": "Арендаторы"}]

    filled = enrich_counterparties_with_folders(
        cps,
        tenant=SimpleNamespace(
            id=1,
            one_c_login="",
            one_c_password="",
            one_c_base_url="",
            nova_organization_id=None,
            one_c_connection_mode="nova_org",
        ),
        nova_client=FakeNova(),
    )
    assert filled == 1
    assert cps[0].folder_name == "Арендаторы"
