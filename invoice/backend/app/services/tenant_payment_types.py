"""Какие виды оплат включены у арендатора (настройка в админке)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.invoice_service_type import ServiceType

_DEFAULT_ENABLED = True


def _is_enabled(tenant: Any, attr: str) -> bool:
    raw = getattr(tenant, attr, None)
    if raw is None:
        return _DEFAULT_ENABLED
    return bool(raw)


def tenant_payment_types_enabled(tenant: Any) -> Dict[str, bool]:
    return {
        "rent": _is_enabled(tenant, "payment_rent_enabled"),
        "utilities": _is_enabled(tenant, "payment_utilities_enabled"),
        "operations": _is_enabled(tenant, "payment_operations_enabled"),
    }


def enabled_service_types_for_tenant(tenant: Any) -> List[ServiceType]:
    enabled = tenant_payment_types_enabled(tenant)
    out: List[ServiceType] = []
    if enabled.get("rent"):
        out.append("rent")
    if enabled.get("utilities"):
        out.append("utilities")
    if enabled.get("operations"):
        out.append("operations")
    return out


def filter_service_types(types: List[ServiceType], tenant: Any) -> List[ServiceType]:
    enabled = tenant_payment_types_enabled(tenant)
    return [t for t in types if enabled.get(t, _DEFAULT_ENABLED)]


def payment_due_days_for_tenant(tenant: Any) -> Dict[str, int]:
    """Сроки оплаты только для включённых видов."""
    enabled = tenant_payment_types_enabled(tenant)
    days = {
        "rent": (getattr(tenant, "invoice_due_day", None) or 5),
        "utilities": (getattr(tenant, "invoice_due_day_utilities", None) or 5),
        "operations": (getattr(tenant, "invoice_due_day_operations", None) or 5),
    }
    return {k: int(v) for k, v in days.items() if enabled.get(k, _DEFAULT_ENABLED)}
