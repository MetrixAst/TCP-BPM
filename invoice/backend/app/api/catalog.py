from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import security_scheme
from app.api.tenant_scope import get_portal_tenant_ids, scoped_tenant_id
from app.db.database import get_db
from app.models.catalog import CounterpartyPhone, TRC, Tenant
from app.schemas.catalog import TRCResponse, TRCWithTenantsResponse, TenantPublicResponse
from app.services.invoice_access import get_trc_id_for_tenant
from app.services.phone_list import join_phone_values, split_phone_values
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id

router = APIRouter()


class CounterpartyPhonesResponse(BaseModel):
    phones: List[str]
    phone_rent: Optional[str] = None
    phone_utilities: Optional[str] = None
    phone_operations: Optional[str] = None
    auto_notify_paused: bool = False
    one_c_synced: Optional[bool] = None
    one_c_message: Optional[str] = None


class CounterpartyPhoneRoutingRequest(BaseModel):
    one_c_counterparty_id: str = Field(..., min_length=1, max_length=64)
    phone_rent: Optional[str] = Field(None, max_length=32)
    phone_utilities: Optional[str] = Field(None, max_length=32)
    phone_operations: Optional[str] = Field(None, max_length=32)
    counterparty_name: Optional[str] = Field(None, max_length=255)


class CounterpartyPhoneAppendRequest(BaseModel):
    one_c_counterparty_id: str = Field(..., min_length=1, max_length=64)
    phone: str = Field(..., min_length=10, max_length=32)
    counterparty_name: Optional[str] = Field(None, max_length=255)


class CounterpartyAutoNotifyRequest(BaseModel):
    one_c_counterparty_id: str = Field(..., min_length=1, max_length=64)
    paused: bool
    counterparty_name: Optional[str] = Field(None, max_length=255)


class TenantAutoNotifyRequest(BaseModel):
    paused: bool


class TenantAutoNotifyResponse(BaseModel):
    auto_notify_paused: bool


@router.get("/trcs", response_model=List[TRCResponse])
async def list_active_trcs(db: Session = Depends(get_db)):
    return (
        db.query(TRC)
        .filter(TRC.is_active.is_(True))
        .order_by(TRC.name)
        .all()
    )


@router.get("/trcs/{trc_id}/tenants", response_model=List[TenantPublicResponse])
async def list_active_tenants(
    trc_id: int,
    db: Session = Depends(get_db),
    credentials=Depends(security_scheme),
):
    trc = db.query(TRC).filter(TRC.id == trc_id, TRC.is_active.is_(True)).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    portal = get_portal_tenant_ids(credentials)
    if portal:
        if portal.get("role") == "tenant":
            tenant_id = portal.get("tenant_id")
            if not tenant_id:
                raise HTTPException(status_code=403, detail="Арендатор не найден")
            return (
                db.query(Tenant)
                .filter(
                    Tenant.id == tenant_id,
                    Tenant.trc_id == trc_id,
                    Tenant.is_active.is_(True),
                )
                .order_by(Tenant.name)
                .all()
            )
        if portal.get("trc_id") != trc_id:
            raise HTTPException(status_code=403, detail="Доступ только к вашему ТРЦ")
    return (
        db.query(Tenant)
        .filter(Tenant.trc_id == trc_id, Tenant.is_active.is_(True))
        .order_by(Tenant.name)
        .all()
    )


@router.get("/trcs/{trc_id}/full", response_model=TRCWithTenantsResponse)
async def get_trc_with_tenants(trc_id: int, db: Session = Depends(get_db)):
    trc = db.query(TRC).filter(TRC.id == trc_id, TRC.is_active.is_(True)).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    tenants = (
        db.query(Tenant)
        .filter(Tenant.trc_id == trc_id, Tenant.is_active.is_(True))
        .order_by(Tenant.name)
        .all()
    )
    return TRCWithTenantsResponse(
        id=trc.id,
        name=trc.name,
        is_active=trc.is_active,
        created_at=trc.created_at,
        tenants=tenants,
    )


def _phone_row_for_counterparty(
    db: Session,
    trc_id: int,
    counterparty_id: str,
) -> Optional[CounterpartyPhone]:
    return (
        db.query(CounterpartyPhone)
        .filter(
            CounterpartyPhone.trc_id == trc_id,
            CounterpartyPhone.one_c_counterparty_id.ilike(counterparty_id.strip()),
        )
        .first()
    )


def _phones_response(
    row: Optional[CounterpartyPhone],
    *,
    one_c_synced: Optional[bool] = None,
    one_c_message: Optional[str] = None,
) -> CounterpartyPhonesResponse:
    phones = split_phone_values(row.phone) if row and row.phone else []
    return CounterpartyPhonesResponse(
        phones=phones,
        phone_rent=(row.phone_rent.strip() if row and row.phone_rent else None),
        phone_utilities=(row.phone_utilities.strip() if row and row.phone_utilities else None),
        phone_operations=(row.phone_operations.strip() if row and row.phone_operations else None),
        auto_notify_paused=bool(row.auto_notify_paused) if row else False,
        one_c_synced=one_c_synced,
        one_c_message=one_c_message,
    )


@router.get("/counterparty-phones", response_model=CounterpartyPhonesResponse)
async def list_counterparty_phones_for_tenant(
    counterparty_id: str = Query(..., min_length=1),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Укажите арендатора (tenant_id)")
    trc_id = get_trc_id_for_tenant(db, tenant_id)
    if not trc_id:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    row = _phone_row_for_counterparty(db, trc_id, counterparty_id)
    return _phones_response(row)


@router.post("/counterparty-phones", response_model=CounterpartyPhonesResponse)
async def append_counterparty_phone(
    body: CounterpartyPhoneAppendRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Добавить телефон контрагенту (несколько номеров через «;» в одной записи)."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Укажите арендатора (tenant_id)")
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    phone = body.phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Укажите номер телефона")

    trc_id = tenant.trc_id
    cp_id = body.one_c_counterparty_id.strip()
    row = (
        db.query(CounterpartyPhone)
        .filter(
            CounterpartyPhone.trc_id == trc_id,
            CounterpartyPhone.one_c_counterparty_id.ilike(cp_id),
        )
        .first()
    )
    existing = split_phone_values(row.phone) if row else []
    already_local = phone in existing
    if not already_local:
        merged = join_phone_values([*existing, phone])
        if row:
            row.phone = merged
            if body.counterparty_name:
                row.counterparty_name = body.counterparty_name
        else:
            row = CounterpartyPhone(
                trc_id=trc_id,
                one_c_counterparty_id=cp_id,
                counterparty_name=body.counterparty_name,
                phone=merged,
            )
            db.add(row)
        db.commit()
        db.refresh(row)
    elif body.counterparty_name and row:
        row.counterparty_name = body.counterparty_name
        db.commit()
        db.refresh(row)

    from app.services.counterparty_contact_sync import (
        refresh_counterparties_after_phone_write,
        sync_counterparty_phones_to_1c,
    )

    integration = get_integration_for_tenant(db, tenant_id)
    try:
        # Синхронный HTTP-запрос к 1С — без threadpool подвешивает единственный
        # uvicorn-воркер (см. аудит от 2026-08-25).
        sync_result = await run_in_threadpool(
            sync_counterparty_phones_to_1c, integration, cp_id, [phone]
        )
    finally:
        if hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass

    # OData (City Mall): номер обязан сесть в 1С. Наша БД уже сохранена.
    if sync_result.get("supported") and not sync_result.get("ok"):
        detail = "; ".join(sync_result.get("messages") or []) or (
            "Не удалось сохранить телефон в 1С"
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"Номер сохранён на платформе, но не записался в 1С: {detail}. "
                "Проверьте права OData на регистр контактной информации."
            ),
        )

    if sync_result.get("supported") and sync_result.get("ok"):
        refresh_counterparties_after_phone_write(db, tenant_id)

    return _phones_response(
        row,
        one_c_synced=bool(sync_result.get("supported") and sync_result.get("ok")),
        one_c_message=(
            None
            if sync_result.get("supported")
            else "Запись в 1С для этого арендатора не поддерживается (нужен OData / Nova OData)"
        ),
    )


@router.patch("/counterparty-phones/routing", response_model=CounterpartyPhonesResponse)
async def update_counterparty_phone_routing(
    body: CounterpartyPhoneRoutingRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Назначить номер для аренды, коммуналки и эксплуатации (авто-рассылка и ручная отправка)."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Укажите арендатора (tenant_id)")
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    trc_id = tenant.trc_id
    cp_id = body.one_c_counterparty_id.strip()
    row = _phone_row_for_counterparty(db, trc_id, cp_id)
    if not row:
        raise HTTPException(status_code=404, detail="Сначала добавьте телефоны контрагенту")

    all_phones = split_phone_values(row.phone)

    def _validate_choice(value: Optional[str], label: str) -> Optional[str]:
        if not value:
            return None
        v = value.strip()
        if v not in all_phones:
            raise HTTPException(
                status_code=400,
                detail=f"{label} должен быть одним из сохранённых номеров контрагента",
            )
        return v

    row.phone_rent = _validate_choice(body.phone_rent, "Номер для аренды")
    row.phone_utilities = _validate_choice(body.phone_utilities, "Номер для коммуналки")
    row.phone_operations = _validate_choice(
        body.phone_operations, "Номер для эксплуатации и маркетинга"
    )
    if body.counterparty_name:
        row.counterparty_name = body.counterparty_name
    db.commit()
    db.refresh(row)
    return _phones_response(row)


@router.patch("/counterparty-phones/auto-notify", response_model=CounterpartyPhonesResponse)
async def update_counterparty_auto_notify(
    body: CounterpartyAutoNotifyRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Поставить/снять паузу авто-рассылки для контрагента (не трогает ручную
    отправку и массовую /send-debtors — см. AutoNotificationService.run_for_tenant)."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Укажите арендатора (tenant_id)")
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    trc_id = tenant.trc_id
    cp_id = body.one_c_counterparty_id.strip()
    row = _phone_row_for_counterparty(db, trc_id, cp_id)
    if not row:
        # Контрагент без сохранённого телефона (номер приходит из 1С) — тоже
        # можно поставить на паузу, создаём запись только под этот флаг.
        row = CounterpartyPhone(
            trc_id=trc_id,
            one_c_counterparty_id=cp_id,
            counterparty_name=body.counterparty_name,
            phone="",
        )
        db.add(row)
    elif body.counterparty_name:
        row.counterparty_name = body.counterparty_name

    row.auto_notify_paused = body.paused
    db.commit()
    db.refresh(row)
    return _phones_response(row)


@router.patch("/tenant/auto-notify", response_model=TenantAutoNotifyResponse)
async def update_tenant_auto_notify(
    body: TenantAutoNotifyRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """«Отключить авто-напоминания для всех» — арендатор ставит на паузу
    AutoNotificationService.run_for_tenant целиком для себя (все контрагенты),
    независимо от точечных пауз по отдельным контрагентам (см. auto-notify
    endpoint выше). Проверяется первым в run_for_tenant, до обращения к 1С."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Укажите арендатора (tenant_id)")
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    tenant.auto_notify_paused = body.paused
    db.commit()
    db.refresh(tenant)
    return TenantAutoNotifyResponse(auto_notify_paused=tenant.auto_notify_paused)
