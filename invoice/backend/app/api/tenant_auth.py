from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import security_scheme
from app.api.tenant_scope import get_portal_tenant_ids
from app.core.security import (
    create_tenant_portal_token,
    create_trc_portal_token,
    verify_password,
)
from app.db.database import get_db
from app.models.catalog import TRC, Tenant
from app.services.tenant_payment_types import tenant_payment_types_enabled

router = APIRouter()


class TenantPortalLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class TenantPortalLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "tenant"
    tenant_id: Optional[int] = None
    trc_id: int
    tenant_name: str = ""
    trc_name: str
    legal_name: str = ""


class TenantPortalMeResponse(BaseModel):
    role: str = "tenant"
    tenant_id: Optional[int] = None
    trc_id: int
    tenant_name: str = ""
    trc_name: str
    legal_name: str = ""
    payment_types_enabled: Optional[dict[str, bool]] = None
    # И парсер под этого арендатора реально написан (Tenant.xlsx_parser_key
    # не пусто), И админ включил xlsx (xlsx_priority != "disabled") — оба
    # условия сразу, иначе можно было бы получить кнопку "Загрузить Excel"
    # в invoice-client для ТЦ, для которого парсера ещё нет, и каждая
    # загрузка падала бы 422 (см. предупреждение при проектировании фичи
    # 2026-08-26). По умолчанию false —xlsx выключен у всех, пока админ
    # явно не включит для конкретного ТЦ.
    xlsx_upload_available: bool = False


@router.post("/login", response_model=TenantPortalLoginResponse)
async def tenant_portal_login(data: TenantPortalLoginRequest, db: Session = Depends(get_db)):
    username = data.username.strip()
    tenant = (
        db.query(Tenant)
        .filter(
            Tenant.portal_username == username,
            Tenant.is_active.is_(True),
        )
        .first()
    )
    if tenant and tenant.portal_password_hash:
        if verify_password(data.password, tenant.portal_password_hash):
            trc = db.query(TRC).filter(TRC.id == tenant.trc_id).first()
            if not trc or not trc.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="ТРЦ арендатора недоступен",
                )
            token = create_tenant_portal_token(tenant.id, tenant.trc_id)
            return TenantPortalLoginResponse(
                access_token=token,
                role="tenant",
                tenant_id=tenant.id,
                trc_id=tenant.trc_id,
                tenant_name=tenant.name,
                trc_name=trc.name,
                legal_name=tenant.legal_name,
            )

    trc = (
        db.query(TRC)
        .filter(
            TRC.portal_username == username,
            TRC.is_active.is_(True),
        )
        .first()
    )
    if trc and trc.portal_password_hash and verify_password(data.password, trc.portal_password_hash):
        token = create_trc_portal_token(trc.id)
        return TenantPortalLoginResponse(
            access_token=token,
            role="trc",
            tenant_id=None,
            trc_id=trc.id,
            tenant_name="",
            trc_name=trc.name,
            legal_name="",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный логин или пароль",
    )


@router.get("/me", response_model=TenantPortalMeResponse)
async def tenant_portal_me(
    db: Session = Depends(get_db),
    credentials=Depends(security_scheme),
):
    portal = get_portal_tenant_ids(credentials)
    if not portal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход арендатора",
        )
    trc = db.query(TRC).filter(TRC.id == portal["trc_id"]).first()
    if portal.get("role") == "trc":
        # Та же логика "один активный Tenant на ТРЦ", что и resolve_tenant_id
        # (см. tenant_scope.py) — сегодня у каждого ТРЦ ровно один. При
        # нескольких xlsx-загрузка недоступна с этого экрана до появления
        # выбора конкретного арендатора (как и сам resolve_tenant_id требует
        # явный tenant_id в этом случае).
        own_tenants = (
            db.query(Tenant)
            .filter(Tenant.trc_id == portal["trc_id"], Tenant.is_active.is_(True))
            .all()
        )
        xlsx_available = (
            len(own_tenants) == 1
            and bool(own_tenants[0].xlsx_parser_key)
            and own_tenants[0].xlsx_priority != "disabled"
        )
        return TenantPortalMeResponse(
            role="trc",
            tenant_id=None,
            trc_id=portal["trc_id"],
            trc_name=trc.name if trc else "",
            xlsx_upload_available=xlsx_available,
        )
    tenant_id = portal.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Арендатор не найден",
        )
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.is_active.is_(True))
        .first()
    )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Арендатор не найден",
        )
    return TenantPortalMeResponse(
        role="tenant",
        tenant_id=tenant.id,
        trc_id=tenant.trc_id,
        tenant_name=tenant.name,
        trc_name=trc.name if trc else "",
        legal_name=tenant.legal_name,
        payment_types_enabled=tenant_payment_types_enabled(tenant),
        xlsx_upload_available=bool(tenant.xlsx_parser_key) and tenant.xlsx_priority != "disabled",
    )
