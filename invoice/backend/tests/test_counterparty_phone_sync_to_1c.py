from unittest.mock import MagicMock, patch

from app.services.counterparty_contact_sync import (
    _normalize_upsert_result,
    sync_counterparty_phones_to_1c,
)
from app.services.counterparty_phone_backfill import backfill_counterparty_phones_to_1c
from app.services.nova_buh_1c_client import NovaBuh1CClient
from app.services.nova_mcp_relay import call_buh_contacts_set


def test_normalize_upsert_result_dict_and_bool():
    assert _normalize_upsert_result({"ok": True, "action": "create"})["ok"] is True
    assert _normalize_upsert_result(False)["ok"] is False
    assert _normalize_upsert_result(False)["action"] == "skip"


def test_sync_phones_odata_success_triggers_written():
    client = MagicMock()
    client.PHONE_CONTACT_KINDS = ("mobile-vid",)
    client.upsert_counterparty_phone.return_value = {
        "ok": True,
        "action": "create",
        "message": "",
    }
    integration = MagicMock()
    integration.client = client
    integration._uses_odata = True

    result = sync_counterparty_phones_to_1c(
        integration,
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ["+77001112233"],
    )
    assert result["ok"] is True
    assert result["supported"] is True
    assert result["written"] == 1
    client.upsert_counterparty_phone.assert_called_once()


def test_sync_phones_odata_failure():
    client = MagicMock()
    client.PHONE_CONTACT_KINDS = ("mobile-vid",)
    client.upsert_counterparty_phone.return_value = {
        "ok": False,
        "action": "create",
        "message": "HTTP 403",
    }
    integration = MagicMock()
    integration.client = client
    integration._uses_odata = True

    result = sync_counterparty_phones_to_1c(
        integration,
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ["+77001112233"],
    )
    assert result["ok"] is False
    assert result["supported"] is True
    assert result["failed"]


def test_sync_phones_nova_com_unsupported_does_not_crash():
    client = MagicMock()
    client.PHONE_CONTACT_KINDS = ()
    client.upsert_counterparty_phone.return_value = {
        "ok": False,
        "action": "skip",
        "message": "not supported",
    }
    client._ensure_agent_id = MagicMock()
    client._odata_org = False
    integration = MagicMock()
    integration.client = client
    integration._uses_odata = False
    type(client).__name__ = "NovaBuh1CClient"

    result = sync_counterparty_phones_to_1c(
        integration,
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ["+77001112233"],
    )
    assert result["supported"] is False
    assert result["ok"] is False


def test_sync_phones_nova_odata_supported():
    client = MagicMock()
    client.PHONE_CONTACT_KINDS = ("f9e52726-2faf-4dca-85d0-559b80df2c53",)
    client.upsert_counterparty_phone.return_value = {
        "ok": True,
        "action": "create",
        "message": "",
    }
    client._ensure_agent_id = MagicMock()
    client._odata_org = True
    integration = MagicMock()
    integration.client = client
    integration._uses_odata = False
    type(client).__name__ = "NovaBuh1CClient"

    result = sync_counterparty_phones_to_1c(
        integration,
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ["+77001112233"],
    )
    assert result["supported"] is True
    assert result["ok"] is True
    assert result["written"] == 1


def test_nova_upsert_calls_contacts_set():
    client = NovaBuh1CClient(organization_id=118)
    client._agent_lookup_done = True
    client._agent_id = "odata-citymall"
    client._odata_org = True

    with (
        patch(
            "app.services.nova_buh_1c_client.relay_configured",
            return_value=True,
        ),
        patch(
            "app.services.nova_buh_1c_client.call_buh_contacts_set",
            return_value={"ok": True, "action": "create", "message": ""},
        ) as mock_set,
    ):
        result = client.upsert_counterparty_phone(
            "78243b44-6f2e-11ef-857e-5254001b9c43",
            "+77005550011",
        )
    assert result["ok"] is True
    assert result["action"] == "create"
    mock_set.assert_called_once()
    kwargs = mock_set.call_args.kwargs
    assert kwargs["agent_id"] == "odata-citymall"
    assert kwargs["object_id"] == "78243b44-6f2e-11ef-857e-5254001b9c43"
    assert kwargs["vid"] == NovaBuh1CClient.CONTACT_KIND_MOBILE


def test_call_buh_contacts_set_parses_processed_item():
    payload = {
        "success": True,
        "result": {
            "ok": True,
            "results": {
                "processed": {
                    "count": 1,
                    "items": [{"ok": True, "action": "update"}],
                }
            },
        },
    }
    with patch(
        "app.services.nova_mcp_relay.call_relay_tool",
        return_value=payload,
    ):
        item = call_buh_contacts_set(
            agent_id="odata-citymall",
            object_id="78243b44-6f2e-11ef-857e-5254001b9c43",
            value="+7 700 555 00 11",
            vid="f9e52726-2faf-4dca-85d0-559b80df2c53",
        )
    assert item["ok"] is True
    assert item["action"] == "update"


def test_backfill_dry_run_lists_phones():
    tenant = MagicMock()
    tenant.id = 2
    tenant.name = "City Mall"
    tenant.trc_id = 2

    row = MagicMock()
    row.one_c_counterparty_id = "cp-1"
    row.counterparty_name = "ИП Тест"
    row.phone = "+77001112233"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = tenant
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

    nova_client = MagicMock()
    nova_client._ensure_agent_id = MagicMock()
    nova_client._odata_org = True
    type(nova_client).__name__ = "NovaBuh1CClient"
    integration = MagicMock()
    integration.client = nova_client
    integration._uses_odata = False

    with patch(
        "app.services.counterparty_phone_backfill.get_integration_for_tenant",
        return_value=integration,
    ):
        result = backfill_counterparty_phones_to_1c(db, tenant_id=2, dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["ok_count"] == 1
    assert result["items"][0]["status"] == "would_write"
