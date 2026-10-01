"""Дефолтные Nova script id для MCP mynova (OData vs COM)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

NOVA_MCP_ODATA = "odata"
NOVA_MCP_COM = "com"

NOVA_SCRIPT_DEFAULTS: dict[str, dict[str, int]] = {
    NOVA_MCP_ODATA: {
        "invoices": 11,
        "payments": 12,
        "counterparties": 13,
        "balance": 14,
        "invoice_by_id": 15,
    },
    NOVA_MCP_COM: {
        "invoices": 16,
        "payments": 17,
        "counterparties": 18,
        "balance": 19,
        "invoice_by_id": 20,
    },
}

_TENANT_SCRIPT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("nova_script_invoices", "invoices"),
    ("nova_script_payments", "payments"),
    ("nova_script_counterparties", "counterparties"),
    ("nova_script_balance", "balance"),
    ("nova_script_invoice_by_id", "invoice_by_id"),
)

if TYPE_CHECKING:
    from app.models.catalog import Tenant


def normalize_nova_mcp_system_type(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if raw in NOVA_SCRIPT_DEFAULTS:
        return raw
    return NOVA_MCP_COM


def nova_script_defaults_for_type(mcp_type: Optional[str]) -> dict[str, int]:
    return dict(NOVA_SCRIPT_DEFAULTS[normalize_nova_mcp_system_type(mcp_type)])


def tenant_nova_script_mapping(tenant: Optional["Tenant"]) -> dict[str, int]:
    """Явные script id арендатора (из tenant), без глобальных дефолтов.

    NOVA_SCRIPT_DEFAULTS — это id только двух конкретных организаций (118 для
    oData, 119 для COM), исторически захардкоженные как "дефолты по типу".
    У каждой организации в Nova свой независимый набор id (см.
    BUH-API-reference/window.BUH_IDS — org 127 и 41 используют совсем другие
    номера, а не 11-15/16-20) — подставлять их для любого другого арендатора
    неверно и раньше приводило к "404 script not found" или (хуже) к тихому
    несовпадению. Пустые поля здесь оставляем отсутствующими в результате —
    NovaBuh1CClient._ensure_scripts сам довосстанавливает недостающие id живым
    resolve_script_ids по названию скрипта в Nova, а не по нашим предположениям.
    """
    mapping: dict[str, int] = {}
    for col, key in _TENANT_SCRIPT_COLUMNS:
        raw = getattr(tenant, col, None) if tenant else None
        if raw is None:
            continue
        try:
            script_id = int(raw)
        except (TypeError, ValueError):
            script_id = 0
        if script_id > 0:
            mapping[key] = script_id
    return mapping
