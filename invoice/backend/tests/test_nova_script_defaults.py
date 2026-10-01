from types import SimpleNamespace

from app.services.nova_script_defaults import (
    NOVA_MCP_COM,
    NOVA_MCP_ODATA,
    nova_script_defaults_for_type,
    tenant_nova_script_mapping,
)


def test_nova_script_defaults_odata():
    defaults = nova_script_defaults_for_type(NOVA_MCP_ODATA)
    assert defaults == {
        "invoices": 11,
        "payments": 12,
        "counterparties": 13,
        "balance": 14,
        "invoice_by_id": 15,
    }


def test_nova_script_defaults_com():
    defaults = nova_script_defaults_for_type(NOVA_MCP_COM)
    assert defaults == {
        "invoices": 16,
        "payments": 17,
        "counterparties": 18,
        "balance": 19,
        "invoice_by_id": 20,
    }


def test_tenant_nova_script_mapping_no_fallback_to_type_defaults():
    """tenant_nova_script_mapping deliberately does NOT fall back to the 118/119
    NOVA_SCRIPT_DEFAULTS for tenants with no explicit script id columns set — each
    Nova org has its own independent id numbering (org 127 uses 71-75, not 11-15),
    so applying another org's defaults previously caused "404 script not found" or
    silent id mismatches. Missing columns must stay absent; NovaBuh1CClient resolves
    them live via resolve_script_ids instead. See nova_script_defaults.py docstring."""
    tenant = SimpleNamespace(
        nova_mcp_system_type=NOVA_MCP_ODATA,
        nova_script_invoices=None,
        nova_script_payments=None,
        nova_script_counterparties=None,
        nova_script_balance=None,
        nova_script_invoice_by_id=None,
    )
    assert tenant_nova_script_mapping(tenant) == {}


def test_tenant_nova_script_mapping_custom_override():
    tenant = SimpleNamespace(
        nova_mcp_system_type=NOVA_MCP_COM,
        nova_script_invoices=21,
        nova_script_payments=17,
        nova_script_counterparties=18,
        nova_script_balance=19,
        nova_script_invoice_by_id=20,
    )
    mapping = tenant_nova_script_mapping(tenant)
    assert mapping["invoices"] == 21
    assert mapping["payments"] == 17
