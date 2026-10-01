from typing import Optional

from sqlalchemy.orm import Session

from app.models.catalog import TRC, Tenant
from app.services.tenant_1c import get_tenant_by_id
from app.services.whatsapp_service import WhatsAppService


def get_trc_by_id(db: Session, trc_id: Optional[int]) -> Optional[TRC]:
    if not trc_id:
        return None
    return db.query(TRC).filter(TRC.id == trc_id, TRC.is_active.is_(True)).first()


def get_trc_for_tenant(db: Session, tenant_id: Optional[int]) -> Optional[TRC]:
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    return get_trc_by_id(db, tenant.trc_id)


def get_whatsapp_for_tenant(db: Session, tenant_id: Optional[int]) -> WhatsAppService:
    tenant = get_tenant_by_id(db, tenant_id)
    trc = get_trc_for_tenant(db, tenant_id)
    return WhatsAppService.for_tenant(tenant, trc)


def get_whatsapp_for_trc(db: Session, trc_id: Optional[int]) -> WhatsAppService:
    trc = get_trc_by_id(db, trc_id)
    return WhatsAppService.for_trc(trc)
