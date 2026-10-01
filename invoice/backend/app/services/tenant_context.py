from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.payment import PaymentFilter
from app.services.tenant_1c import get_tenant_by_id


def apply_tenant_to_filters(
    db: Session,
    tenant_id: Optional[int],
    filters: PaymentFilter,
    ip_name: Optional[str],
    tenant_name: Optional[str],
) -> PaymentFilter:

    if ip_name:
        filters.ip_name = ip_name
    if tenant_name:
        filters.tenant_name = tenant_name
    return filters
