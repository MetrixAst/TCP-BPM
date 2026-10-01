"""Resolve Nova organization config for admin auto-fill."""

from __future__ import annotations

from app.schemas.catalog import NovaOrgResolveResponse
from app.services.nova_1c_service import Nova1CServiceError, get_nova_1c_service
from app.services.nova_script_defaults import (
    NOVA_MCP_COM,
    NOVA_MCP_ODATA,
    nova_script_defaults_for_type,
)
from app.services.tenant_1c import CONNECTION_MODE_NOVA, CONNECTION_MODE_ODATA


def _script_fields_for_response(
    mcp_type: str,
    *,
    resolved: dict[str, int] | None = None,
) -> dict[str, int]:
    """Merge org-resolved script ids with MCP-type defaults (per-client when available)."""
    defaults = nova_script_defaults_for_type(mcp_type)
    merged = {**defaults, **(resolved or {})}
    return {
        "nova_script_invoices": merged["invoices"],
        "nova_script_payments": merged["payments"],
        "nova_script_counterparties": merged["counterparties"],
        "nova_script_balance": merged["balance"],
        "nova_script_invoice_by_id": merged["invoice_by_id"],
    }


def _resolve_org_scripts(service, organization_id: int) -> dict[str, int]:
    try:
        return service.resolve_script_ids(organization_id)
    except Nova1CServiceError:
        return {}


def resolve_nova_organization(organization_id: int, *, test_connection: bool = True) -> NovaOrgResolveResponse:
    service = get_nova_1c_service()
    org_name = None
    error = None
    test_ok = False
    counterparties_count = None

    if not service.configured():
        return NovaOrgResolveResponse(
            organization_id=organization_id,
            connection_mode=CONNECTION_MODE_NOVA,
            nova_mcp_system_type=NOVA_MCP_COM,
            **_script_fields_for_response(NOVA_MCP_COM),
            password_required=False,
            message=(
                "Nova API не настроен на сервере (NOVA_BACKEND_URL, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD). "
                "Для OData org_id можно заполнить поля вручную."
            ),
            test_ok=False,
            error="nova_not_configured",
        )

    try:
        config = service.get_org_config(organization_id)
        org_name = service.get_organization_name(organization_id)
    except Nova1CServiceError as exc:
        return NovaOrgResolveResponse(
            organization_id=organization_id,
            connection_mode=CONNECTION_MODE_NOVA,
            nova_mcp_system_type=NOVA_MCP_COM,
            **_script_fields_for_response(NOVA_MCP_COM),
            message=str(exc),
            test_ok=False,
            error=str(exc),
        )

    mcp_type = NOVA_MCP_ODATA if config.odata_url else NOVA_MCP_COM
    resolved_scripts = _resolve_org_scripts(service, organization_id)
    script_fields = _script_fields_for_response(mcp_type, resolved=resolved_scripts)

    if config.odata_url:
        response = NovaOrgResolveResponse(
            organization_id=organization_id,
            organization_name=org_name,
            connection_mode=CONNECTION_MODE_ODATA,
            nova_mcp_system_type=mcp_type,
            **script_fields,
            odata_url=config.odata_url,
            one_c_login=config.username,
            database_name=config.database_name,
            agent_id=config.agent_id,
            password_required=True,
            message=(
                "OData: URL и логин подставлены из Nova. Пароль 1С введите вручную "
                "(Nova не отдаёт пароль). Для MCP mynova выберите режим «MCP mynova» "
                f"и тип «{mcp_type}» — скрипты org {organization_id}: "
                f"{script_fields['nova_script_invoices']}–"
                f"{script_fields['nova_script_invoice_by_id']}."
            ),
        )
    else:
        response = NovaOrgResolveResponse(
            organization_id=organization_id,
            organization_name=org_name,
            connection_mode=CONNECTION_MODE_NOVA,
            nova_mcp_system_type=mcp_type,
            **script_fields,
            database_name=config.database_name,
            password_required=False,
            message=(
                f"COM/MCP: подключение через Nova scripts для org_id {organization_id} "
                f"({script_fields['nova_script_invoices']}–"
                f"{script_fields['nova_script_invoice_by_id']}). "
                "URL и пароль 1С не нужны — нужны права «Внешнее соединение» в 1С."
            ),
        )

    if test_connection:
        try:
            # Always test the counterparties script resolved for THIS org,
            # not the global OData/COM defaults (11–15 / 16–20).
            cp_script = script_fields["nova_script_counterparties"]
            payload = service.run_script(organization_id, cp_script)
            if payload.get("ok") is False:
                error = str(
                    payload.get("error_message") or payload.get("error") or "script failed"
                )
            else:
                results = payload.get("result", {}).get("results", {})
                items = results.get("counterparties", {}).get("items")
                if items is None:
                    batch = results.get("batch")
                    if isinstance(batch, dict) and isinstance(batch.get("batch"), list):
                        for entry in reversed(batch["batch"]):
                            if isinstance(entry, dict) and isinstance(entry.get("items"), list):
                                items = entry["items"]
                                break
                counterparties_count = len(items or [])
                test_ok = True
        except Nova1CServiceError as exc:
            error = str(exc)

    response.test_ok = test_ok
    response.counterparties_count = counterparties_count
    if error:
        response.error = error
        if not test_ok:
            response.message = f"{response.message} Проверка: {error}"
    elif test_ok and counterparties_count is not None:
        response.message = f"{response.message} Проверка OK: {counterparties_count} контрагентов."

    return response
