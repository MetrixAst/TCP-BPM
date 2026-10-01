from app.services.nova_buh_1c_client import NovaBuh1CClient


class _DummyService:
    def resolve_script_ids(self, organization_id: int):
        return {}


def test_get_invoice_counterparty_id_relaxed_guid_match_from_cache():
    client = NovaBuh1CClient(organization_id=119, service=_DummyService())
    client._invoice_headers_by_id = {
        "4a958ab0-5da9-11f1-b51d-4c526260eadc": {"counterparty_id": "cp-guid-1"}
    }
    assert (
        client.get_invoice_counterparty_id("4a958ab0-5da9-11f1-b51c-4c526260eadc")
        == "cp-guid-1"
    )
