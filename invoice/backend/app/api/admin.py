import logging
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.models.catalog import AdminUser, CounterpartyPhone, TRC, Tenant
from app.models.counterparty_balance import CounterpartyBalance
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.payment import TenantPayment
from app.schemas.catalog import (
    AdminLoginRequest,
    AdminTokenResponse,
    AdminUserResponse,
    CounterpartyDirectoryItem,
    CounterpartyPhoneBackfillResponse,
    CounterpartyPhoneResponse,
    CounterpartyPhoneUpsert,
    TRCCreate,
    TRCAdminResponse,
    TRCResponse,
    TRCUpdate,
    TenantAdminResponse,
    TenantCreate,
    TenantUpdate,
    NovaOrgResolveResponse,
    SmtpTestRequest,
    SmtpTestResponse,
    TrcDebtSummary,
)
from app.schemas.notification import NotificationSend, WhatsAppLogResponse
from app.services.counterparty_balance_service import trc_debt_summary
from app.services.notification_service import NotificationService
from app.services.nova_org_resolve import resolve_nova_organization
from app.services.smtp_mail import check_smtp_connection, send_smtp_test_email
from app.services.whatsapp_log_service import get_whatsapp_log
from app.services.tenant_stamp import (
    delete_tenant_signature,
    delete_tenant_stamp,
    resolve_signature_path,
    resolve_stamp_path,
    save_tenant_signature,
    save_tenant_stamp,
)

logger = logging.getLogger(__name__)


_PATCH_KEEP_IF_EMPTY = frozenset(
    {
        "one_c_login",
        "one_c_password",
        "one_c_basic_password",
        "green_api_api_token",
        "smtp_password",
    }
)


class AdminUserCreate(BaseModel):
    username: str
    password: str


class AutoNotificationRunRequest(BaseModel):
    tenant_id: Optional[int] = None
    force_window: bool = False


class AutoNotificationRunResponse(BaseModel):
    sent: int
    can_send: bool
    tenant_id: Optional[int] = None


class GreenApiPacingRequest(BaseModel):
    # Green API: 500-600000мс. Дефолт settings.WHATSAPP_SEND_DELAY_SECONDS*1000
    # (45с) — см. инцидент 2026-09-09 (массовая рассылка без паузы, инстанс
    # заблокирован, 104 из 111 счетов не дошли).
    delay_ms: int = Field(ge=500, le=600_000)
    # Явно, а не из settings/окружения — этот URL зависит от домена конкретного
    # окружения (prod/test/dev), у бэкенда нет своего "публичного base URL" в
    # конфиге. Опционально: без него меняется только пейсинг, webhookUrl не
    # трогается (обратная совместимость с уже задеплоенным вызовом).
    webhook_url: Optional[str] = Field(
        default=None,
        description="Напр. https://api.invoice.metrix.com.ai/api/webhooks/green-api — "
        "включает outgoingAPIMessageWebhook, без него доставка не подтверждается никогда "
        "(см. комментарий в whatsapp_service.set_send_delay, инцидент 2026-09-09/обнаружено 2026-09-10)",
    )


class GreenApiPacingResponse(BaseModel):
    success: bool
    id_instance: Optional[str] = None
    delay_ms: int
    webhook_configured: bool = False


class ResendByInvoiceItem(BaseModel):
    # Явно телефон+счёт, а не notification_id — на 2026-09-09 у части
    # уведомлений в БД телефон в Notification.phone_number уже устарел
    # (сменился контакт) или сама Notification-строка не находится по старым
    # критериям, а вот номер и invoice_id были заново сверены напрямую по
    # Green API GetChatHistory (см. scripts/maxi_mall_2026_09_09_stuck_messages.json).
    phone: str
    invoice_id: str


class ResendByInvoiceRequest(BaseModel):
    items: List[ResendByInvoiceItem] = Field(min_length=1, max_length=500)


class ResendByInvoiceItemResult(BaseModel):
    phone: str
    invoice_id: str
    outcome: str  # "queued" | "invalid_phone" | "invoice_not_found" | "already_delivered"
    notification_id: Optional[int] = None


class ResendByInvoiceResponse(BaseModel):
    queued: int
    skipped: int
    results: List[ResendByInvoiceItemResult]


router = APIRouter()


def _portal_username_taken(
    db: Session,
    username: str,
    *,
    exclude_tenant_id: Optional[int] = None,
    exclude_trc_id: Optional[int] = None,
) -> bool:
    tenant_q = db.query(Tenant).filter(Tenant.portal_username == username)
    if exclude_tenant_id is not None:
        tenant_q = tenant_q.filter(Tenant.id != exclude_tenant_id)
    if tenant_q.first():
        return True
    trc_q = db.query(TRC).filter(TRC.portal_username == username)
    if exclude_trc_id is not None:
        trc_q = trc_q.filter(TRC.id != exclude_trc_id)
    return trc_q.first() is not None


def _apply_portal_credentials(
    db: Session,
    tenant: Tenant,
    portal_username: Optional[str],
    portal_password: Optional[str],
) -> None:
    if portal_username is not None:
        username = portal_username.strip()
        if not username:
            tenant.portal_username = None
        else:
            if _portal_username_taken(db, username, exclude_tenant_id=tenant.id):
                raise HTTPException(
                    status_code=400,
                    detail="Логин портала уже занят",
                )
            tenant.portal_username = username
    if portal_password is not None and portal_password.strip():
        if len(portal_password.strip()) < 4:
            raise HTTPException(
                status_code=400,
                detail="Пароль портала не короче 4 символов",
            )
        tenant.portal_password_hash = hash_password(portal_password.strip())


def _apply_trc_portal_credentials(
    db: Session,
    trc: TRC,
    portal_username: Optional[str],
    portal_password: Optional[str],
) -> None:
    if portal_username is not None:
        username = portal_username.strip()
        if not username:
            trc.portal_username = None
        else:
            if _portal_username_taken(db, username, exclude_trc_id=trc.id):
                raise HTTPException(
                    status_code=400,
                    detail="Логин портала уже занят",
                )
            trc.portal_username = username
    if portal_password is not None and portal_password.strip():
        if len(portal_password.strip()) < 4:
            raise HTTPException(
                status_code=400,
                detail="Пароль портала не короче 4 символов",
            )
        trc.portal_password_hash = hash_password(portal_password.strip())


def _tenant_to_admin(tenant: Tenant) -> TenantAdminResponse:
    return TenantAdminResponse(
        id=tenant.id,
        trc_id=tenant.trc_id,
        name=tenant.name,
        legal_name=tenant.legal_name,
        org_type=tenant.org_type,
        bin_value=tenant.bin_value,
        iin_value=tenant.iin_value,
        phone=tenant.phone,
        message_template=tenant.message_template,
        green_api_url=tenant.green_api_url,
        green_api_media_url=tenant.green_api_media_url,
        green_api_id_instance=tenant.green_api_id_instance,
        one_c_counterparty_id=tenant.one_c_counterparty_id,
        one_c_name_match=tenant.one_c_name_match,
        one_c_login=tenant.one_c_login,
        one_c_base_url=tenant.one_c_base_url,
        one_c_basic_user=tenant.one_c_basic_user,
        nova_organization_id=tenant.nova_organization_id,
        nova_mcp_system_type=tenant.nova_mcp_system_type,
        nova_script_invoices=tenant.nova_script_invoices,
        nova_script_payments=tenant.nova_script_payments,
        nova_script_counterparties=tenant.nova_script_counterparties,
        nova_script_balance=tenant.nova_script_balance,
        nova_script_invoice_by_id=tenant.nova_script_invoice_by_id,
        one_c_connection_mode=tenant.one_c_connection_mode,
        xlsx_priority=tenant.xlsx_priority,
        xlsx_parser_key=tenant.xlsx_parser_key,
        portal_username=tenant.portal_username,
        stamp_file_path=tenant.stamp_file_path,
        signature_file_path=tenant.signature_file_path,
        invoice_executor_name=tenant.invoice_executor_name,
        invoice_iik=tenant.invoice_iik,
        invoice_kbe=tenant.invoice_kbe,
        invoice_bank_name=tenant.invoice_bank_name,
        invoice_bank_bik=tenant.invoice_bank_bik,
        invoice_payment_knp=tenant.invoice_payment_knp,
        invoice_supplier_address=tenant.invoice_supplier_address,
        invoice_contract_text=tenant.invoice_contract_text,
        invoice_due_day=tenant.invoice_due_day,
        invoice_due_day_utilities=tenant.invoice_due_day_utilities,
        invoice_due_day_operations=tenant.invoice_due_day_operations,
        payment_rent_enabled=tenant.payment_rent_enabled,
        payment_utilities_enabled=tenant.payment_utilities_enabled,
        payment_operations_enabled=tenant.payment_operations_enabled,
        invoice_operations_advance_billing=tenant.invoice_operations_advance_billing,
        smtp_host=tenant.smtp_host,
        smtp_port=tenant.smtp_port,
        smtp_use_starttls=bool(tenant.smtp_use_starttls)
        if tenant.smtp_use_starttls is not None
        else True,
        smtp_username=tenant.smtp_username,
        smtp_from_email=tenant.smtp_from_email,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        has_one_c_password=bool((tenant.one_c_password or "").strip()),
        has_one_c_basic_password=bool((tenant.one_c_basic_password or "").strip()),
        has_green_api_api_token=bool((tenant.green_api_api_token or "").strip()),
        has_smtp_password=bool((tenant.smtp_password or "").strip()),
    )


@router.get("/nova/organizations/{organization_id}/resolve", response_model=NovaOrgResolveResponse)
async def resolve_nova_org(
    organization_id: int,
    test: bool = Query(True, description="Пробный запрос контрагентов"),
    _: AdminUser = Depends(get_current_admin),
):
    if organization_id < 1:
        raise HTTPException(status_code=400, detail="organization_id должен быть >= 1")
    return resolve_nova_organization(organization_id, test_connection=test)


@router.post("/auth/login", response_model=AdminTokenResponse)
async def admin_login(data: AdminLoginRequest, db: Session = Depends(get_db)):
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.username == data.username, AdminUser.is_active.is_(True))
        .first()
    )
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    token = create_access_token(admin.username)
    return AdminTokenResponse(access_token=token)


@router.get("/me", response_model=AdminUserResponse)
async def admin_me(admin: AdminUser = Depends(get_current_admin)):
    return admin


@router.get("/trcs", response_model=List[TRCAdminResponse])
async def list_trcs(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    return db.query(TRC).order_by(TRC.name).all()


@router.get("/trcs/{trc_id}", response_model=TRCAdminResponse)
async def get_trc(
    trc_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    return trc


@router.post("/trcs", response_model=TRCAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_trc(
    data: TRCCreate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    exists = db.query(TRC).filter(TRC.name == data.name).first()
    if exists:
        raise HTTPException(status_code=400, detail="ТРЦ с таким названием уже существует")
    trc = TRC(**data.model_dump())
    db.add(trc)
    db.commit()
    db.refresh(trc)
    return trc


@router.patch("/trcs/{trc_id}", response_model=TRCAdminResponse)
async def update_trc(
    trc_id: int,
    data: TRCUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    update_data = data.model_dump(exclude_unset=True)
    portal_username = update_data.pop("portal_username", None)
    portal_password = update_data.pop("portal_password", None)
    for key, value in update_data.items():
        setattr(trc, key, value)
    if portal_username is not None or portal_password is not None:
        _apply_trc_portal_credentials(db, trc, portal_username, portal_password)
    db.commit()
    db.refresh(trc)
    return trc


@router.delete("/trcs/{trc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trc(
    trc_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    db.delete(trc)
    db.commit()


@router.get("/trcs/{trc_id}/tenants", response_model=List[TenantAdminResponse])
async def list_tenants(
    trc_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    tenants = db.query(Tenant).filter(Tenant.trc_id == trc_id).order_by(Tenant.name).all()
    return [_tenant_to_admin(t) for t in tenants]


@router.post("/trcs/{trc_id}/tenants", response_model=TenantAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    trc_id: int,
    data: TenantCreate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    tenant = Tenant(
        trc_id=trc_id,
        name=data.name,
        legal_name=data.legal_name,
        org_type=data.org_type,
        bin_value=data.bin_value,
        iin_value=data.iin_value,
        phone=data.phone,
        message_template=data.message_template,
        green_api_url=data.green_api_url,
        green_api_media_url=data.green_api_media_url,
        green_api_id_instance=data.green_api_id_instance,
        green_api_api_token=data.green_api_api_token,
        one_c_counterparty_id=data.one_c_counterparty_id,
        one_c_name_match=data.one_c_name_match,
        one_c_login=data.one_c_login,
        one_c_password=data.one_c_password,
        one_c_base_url=data.one_c_base_url,
        one_c_basic_user=data.one_c_basic_user,
        one_c_basic_password=data.one_c_basic_password,
        nova_organization_id=data.nova_organization_id,
        nova_mcp_system_type=data.nova_mcp_system_type,
        nova_script_invoices=data.nova_script_invoices,
        nova_script_payments=data.nova_script_payments,
        nova_script_counterparties=data.nova_script_counterparties,
        nova_script_balance=data.nova_script_balance,
        nova_script_invoice_by_id=data.nova_script_invoice_by_id,
        one_c_connection_mode=data.one_c_connection_mode or "auto",
        xlsx_priority=data.xlsx_priority or "disabled",
        xlsx_parser_key=data.xlsx_parser_key,
        invoice_executor_name=data.invoice_executor_name,
        invoice_iik=data.invoice_iik,
        invoice_kbe=data.invoice_kbe,
        invoice_bank_name=data.invoice_bank_name,
        invoice_bank_bik=data.invoice_bank_bik,
        invoice_payment_knp=data.invoice_payment_knp,
        invoice_supplier_address=data.invoice_supplier_address,
        invoice_contract_text=data.invoice_contract_text,
        invoice_due_day=data.invoice_due_day,
        invoice_due_day_utilities=data.invoice_due_day_utilities,
        invoice_due_day_operations=data.invoice_due_day_operations,
        payment_rent_enabled=data.payment_rent_enabled,
        payment_utilities_enabled=data.payment_utilities_enabled,
        payment_operations_enabled=data.payment_operations_enabled,
        invoice_operations_advance_billing=data.invoice_operations_advance_billing,
        smtp_host=data.smtp_host,
        smtp_port=data.smtp_port,
        smtp_use_starttls=data.smtp_use_starttls if data.smtp_use_starttls is not None else True,
        smtp_username=data.smtp_username,
        smtp_password=data.smtp_password,
        smtp_from_email=data.smtp_from_email,
        is_active=data.is_active,
    )
    db.add(tenant)
    db.flush()
    _apply_portal_credentials(
        db, tenant, data.portal_username, data.portal_password
    )
    db.commit()
    db.refresh(tenant)
    return _tenant_to_admin(tenant)


@router.patch("/trcs/{trc_id}/tenants/{tenant_id}", response_model=TenantAdminResponse)
async def update_tenant(
    trc_id: int,
    tenant_id: int,
    data: TenantUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    update_data = data.model_dump(exclude_unset=True)
    # Ключевые слова услуг — только встроенные дефолты, не из админки
    update_data.pop("payment_keywords_rent", None)
    update_data.pop("payment_keywords_utilities", None)
    update_data.pop("payment_keywords_operations", None)
    portal_username = update_data.pop("portal_username", None)
    portal_password = update_data.pop("portal_password", None)
    for key in list(update_data.keys()):
        if key not in _PATCH_KEEP_IF_EMPTY:
            continue
        val = update_data[key]
        if val is None or (isinstance(val, str) and not str(val).strip()):
            update_data.pop(key)
    for key, value in update_data.items():
        setattr(tenant, key, value)
    if portal_username is not None or portal_password is not None:
        _apply_portal_credentials(db, tenant, portal_username, portal_password)
    db.commit()
    db.refresh(tenant)
    return _tenant_to_admin(tenant)


@router.post(
    "/trcs/{trc_id}/tenants/{tenant_id}/smtp/test",
    response_model=SmtpTestResponse,
)
async def test_tenant_smtp(
    trc_id: int,
    tenant_id: int,
    data: SmtpTestRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Проверка SMTP арендатора (логин). Опционально send_to — тестовое письмо."""
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    host = (data.smtp_host if data.smtp_host is not None else tenant.smtp_host) or ""
    port = data.smtp_port if data.smtp_port is not None else tenant.smtp_port
    use_tls = (
        data.smtp_use_starttls
        if data.smtp_use_starttls is not None
        else (True if tenant.smtp_use_starttls is None else bool(tenant.smtp_use_starttls))
    )
    username = (
        data.smtp_username if data.smtp_username is not None else tenant.smtp_username
    ) or ""
    password = (data.smtp_password or "").strip() or (tenant.smtp_password or "")
    from_email = (
        data.smtp_from_email if data.smtp_from_email is not None else tenant.smtp_from_email
    ) or username

    if data.send_to and str(data.send_to).strip():
        result = send_smtp_test_email(
            host=host,
            port=int(port or 587),
            username=username,
            password=password,
            use_starttls=use_tls,
            from_email=from_email,
            to_email=str(data.send_to).strip(),
        )
    else:
        result = check_smtp_connection(
            host=host,
            port=int(port or 587),
            username=username,
            password=password,
            use_starttls=use_tls,
            from_email=from_email,
        )
    return SmtpTestResponse(
        ok=bool(result.get("ok")),
        message=result.get("message"),
        error=result.get("error"),
    )


@router.post("/trcs/{trc_id}/tenants/{tenant_id}/stamp", response_model=TenantAdminResponse)
async def upload_tenant_stamp(
    trc_id: int,
    tenant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    delete_tenant_stamp(tenant.stamp_file_path, tenant=tenant)
    rel, png_bytes = save_tenant_stamp(tenant_id, file)
    tenant.stamp_file_path = rel
    tenant.stamp_png = png_bytes
    db.commit()
    db.refresh(tenant)
    if not resolve_stamp_path(tenant.stamp_file_path, tenant_id=tenant.id, tenant=tenant):
        logger.warning(
            "Stamp saved to DB but file missing on disk (tenant_id=%s path=%s). "
            "Set TENANT_UPLOADS_DIR to a shared volume on all API pods.",
            tenant_id,
            tenant.stamp_file_path,
        )
    return _tenant_to_admin(tenant)


@router.get("/trcs/{trc_id}/tenants/{tenant_id}/stamp")
async def get_tenant_stamp(
    trc_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    stamp_path = resolve_stamp_path(tenant.stamp_file_path, tenant_id=tenant.id, tenant=tenant)
    if not stamp_path:
        raise HTTPException(status_code=404, detail="Печать не загружена")
    return FileResponse(stamp_path, media_type="image/png")


@router.delete("/trcs/{trc_id}/tenants/{tenant_id}/stamp", response_model=TenantAdminResponse)
async def remove_tenant_stamp(
    trc_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    delete_tenant_stamp(tenant.stamp_file_path, tenant=tenant)
    tenant.stamp_file_path = None
    db.commit()
    db.refresh(tenant)
    return _tenant_to_admin(tenant)


@router.post("/trcs/{trc_id}/tenants/{tenant_id}/signature", response_model=TenantAdminResponse)
async def upload_tenant_signature(
    trc_id: int,
    tenant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    delete_tenant_signature(tenant.signature_file_path, tenant=tenant)
    rel, png_bytes = save_tenant_signature(tenant_id, file)
    tenant.signature_file_path = rel
    tenant.signature_png = png_bytes
    db.commit()
    db.refresh(tenant)
    if not resolve_signature_path(tenant.signature_file_path, tenant_id=tenant.id, tenant=tenant):
        logger.warning(
            "Signature saved to DB but file missing on disk (tenant_id=%s path=%s). "
            "Set TENANT_UPLOADS_DIR to a shared volume on all API pods.",
            tenant_id,
            tenant.signature_file_path,
        )
    return _tenant_to_admin(tenant)


@router.get("/trcs/{trc_id}/tenants/{tenant_id}/signature")
async def get_tenant_signature(
    trc_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    signature_path = resolve_signature_path(tenant.signature_file_path, tenant_id=tenant.id, tenant=tenant)
    if not signature_path:
        raise HTTPException(status_code=404, detail="Подпись не загружена")
    return FileResponse(signature_path, media_type="image/png")


@router.delete("/trcs/{trc_id}/tenants/{tenant_id}/signature", response_model=TenantAdminResponse)
async def remove_tenant_signature(
    trc_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    delete_tenant_signature(tenant.signature_file_path, tenant=tenant)
    tenant.signature_file_path = None
    db.commit()
    db.refresh(tenant)
    return _tenant_to_admin(tenant)


@router.delete("/trcs/{trc_id}/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    trc_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id)
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    delete_tenant_stamp(tenant.stamp_file_path, tenant=tenant)
    delete_tenant_signature(tenant.signature_file_path, tenant=tenant)
    db.delete(tenant)
    db.commit()


def _first_tenant_for_trc(db: Session, trc_id: int) -> Optional[Tenant]:
    return (
        db.query(Tenant)
        .filter(Tenant.trc_id == trc_id, Tenant.is_active.is_(True))
        .order_by(Tenant.id)
        .first()
    )


@router.get(
    "/trcs/{trc_id}/debt-summary",
    response_model=TrcDebtSummary,
)
async def trc_debt_summary_view(
    trc_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Сводный долг по всем арендаторам ТРЦ — из уже засинканного снимка
    CounterpartyBalance, без живого похода в 1С (быстро, но может отставать
    от последнего sync_counterparty_balances)."""
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    return trc_debt_summary(db, trc_id)


def _looks_like_phone(value: Optional[str]) -> bool:
    """1С иногда отдаёт в поле телефона внутренний добавочный ('58-99-69'),
    а не полный номер. Наш CounterpartyPhoneUpsert.phone требует min_length=10 —
    такое значение, попав в директорию как подсказка, блокирует 422-й весь
    батч сохранения телефонов при каждом клике, пока его не уберут вручную.
    Отсекаем такие значения на входе, чтобы не подставлять их автоматически."""
    if not value:
        return False
    return len(re.sub(r"\D", "", value)) >= 10


@router.get(
    "/trcs/{trc_id}/counterparty-directory",
    response_model=List[CounterpartyDirectoryItem],
)
async def counterparty_directory(
    trc_id: int,
    tenant_id: Optional[int] = Query(None, description="Арендатор для подключения к 1С"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Список контрагентов из 1С + сохранённые телефоны получателей WhatsApp."""
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    tenant = (
        db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id).first()
        if tenant_id
        else _first_tenant_for_trc(db, trc_id)
    )
    if not tenant:
        raise HTTPException(status_code=400, detail="Нет арендатора с доступом к 1С")

    saved = {
        row.one_c_counterparty_id.lower(): row
        for row in db.query(CounterpartyPhone).filter(CounterpartyPhone.trc_id == trc_id).all()
    }

    from app.services.counterparty_cache_service import (
        get_cached_directory_items,
        maybe_schedule_tenant_data_sync,
    )

    # Может уйти в блокирующий KafkaProducer.send().get() (до 15с) — без
    # threadpool подвешивает единственный uvicorn-воркер (см. аудит от 2026-08-25).
    await run_in_threadpool(maybe_schedule_tenant_data_sync, db, tenant.id)

    cached = get_cached_directory_items(db, tenant.id)
    if not cached:
        raise HTTPException(
            status_code=503,
            detail="Список контрагентов загружается из 1С. Повторите через минуту.",
        )

    result: List[CounterpartyDirectoryItem] = []
    for cp in cached:
        key = cp["one_c_counterparty_id"].lower()
        row = saved.get(key)
        contact = cp.get("contact_name") or ""
        cp_phone = cp.get("phone_number")
        result.append(
            CounterpartyDirectoryItem(
                one_c_counterparty_id=cp["one_c_counterparty_id"],
                counterparty_name=cp["counterparty_name"],
                contact_name=contact or (row.contact_name if row else None),
                phone=(row.phone if row else None)
                or (cp_phone if _looks_like_phone(cp_phone) else None),
                bin_value=cp.get("bin_value"),
                last_whatsapp_sent_at=row.last_whatsapp_sent_at if row else None,
            )
        )
    result.sort(key=lambda x: x.counterparty_name.lower())
    return result


@router.get(
    "/trcs/{trc_id}/counterparty-directory-xlsx",
    response_model=List[CounterpartyDirectoryItem],
)
async def counterparty_directory_xlsx(
    trc_id: int,
    tenant_id: int = Query(..., description="Арендатор, чьи xlsx-контрагенты нужны"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Тот же список/форма, что и counterparty_directory (для "Сохранить
    телефоны" ниже по коду фронта), но источник — CounterpartyBalance(
    source="xlsx") вместо живого 1С. Для арендаторов вообще без 1С
    counterparty_directory всегда отдаёт 503 (кэш никогда не наполнится) —
    это параллельный путь, а не замена, см. аудит от 2026-08-26.
    one_c_counterparty_id тут может быть virtual:<hash> (см.
    counterparty_name_match.py), не обязательно настоящий GUID из 1С —
    upsert_counterparty_phones принимает любую строку как ключ, это не
    ломает сохранение."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    saved = {
        row.one_c_counterparty_id.lower(): row
        for row in db.query(CounterpartyPhone).filter(CounterpartyPhone.trc_id == trc_id).all()
    }

    rows = (
        db.query(CounterpartyBalance)
        .filter(CounterpartyBalance.tenant_id == tenant_id, CounterpartyBalance.source == "xlsx")
        .all()
    )
    result: List[CounterpartyDirectoryItem] = []
    for cp_row in rows:
        key = cp_row.counterparty_id.lower()
        saved_row = saved.get(key)
        result.append(
            CounterpartyDirectoryItem(
                one_c_counterparty_id=cp_row.counterparty_id,
                counterparty_name=cp_row.counterparty_name or cp_row.counterparty_id,
                contact_name=saved_row.contact_name if saved_row else None,
                phone=saved_row.phone if saved_row else None,
                bin_value=None,
                last_whatsapp_sent_at=saved_row.last_whatsapp_sent_at if saved_row else None,
            )
        )
    result.sort(key=lambda x: x.counterparty_name.lower())
    return result


@router.get(
    "/trcs/{trc_id}/whatsapp-log",
    response_model=WhatsAppLogResponse,
)
async def whatsapp_log(
    trc_id: int,
    tenant_id: Optional[int] = Query(None, description="Ограничить одним арендатором"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Журнал WhatsApp-отправок: ручные/массовые (Notification) + авто (AutoNotificationLog).
    Не включает /api/notifications/send-file — тот путь никуда не логируется."""
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    items, total = get_whatsapp_log(
        db,
        trc_id=trc_id,
        tenant_id=tenant_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return WhatsAppLogResponse(items=items, total=total)


@router.post(
    "/trcs/{trc_id}/green-api-pacing",
    response_model=GreenApiPacingResponse,
)
async def set_trc_green_api_pacing(
    trc_id: int,
    data: GreenApiPacingRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Green API SetSettings.delaySendMessagesMilliseconds для инстанса ТРЦ —
    сообщения ставятся в FIFO-очередь на стороне Green API и уходят не чаще
    этого интервала, независимо от того, как быстро наш код их шлёт. Опционально
    (webhook_url) — заодно включает outgoingAPIMessageWebhook, без которого
    реальная доставка никогда не подтверждается (см.
    whatsapp_service.set_send_delay и инцидент 2026-09-09/находка 2026-09-10)."""
    if not admin.is_super:
        raise HTTPException(
            status_code=403, detail="Только супер-админ может менять настройки Green API"
        )
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")

    from app.services.whatsapp_service import WhatsAppService

    wa = WhatsAppService.for_trc(trc)
    ok = await run_in_threadpool(wa.set_send_delay, data.delay_ms, data.webhook_url)
    logger.info(
        "Green API pacing set by %s trc=%s delay_ms=%s webhook=%s ok=%s",
        admin.username, trc_id, data.delay_ms, bool(data.webhook_url), ok,
    )
    return GreenApiPacingResponse(
        success=ok, id_instance=wa.id_instance, delay_ms=data.delay_ms,
        webhook_configured=ok and bool(data.webhook_url),
    )


@router.post(
    "/trcs/{trc_id}/tenants/{tenant_id}/green-api-pacing",
    response_model=GreenApiPacingResponse,
)
async def set_tenant_green_api_pacing(
    trc_id: int,
    tenant_id: int,
    data: GreenApiPacingRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Как set_trc_green_api_pacing, но для собственного инстанса конкретного
    арендатора (Tenant.green_api_id_instance/api_token переопределяют ТРЦ —
    см. WhatsAppService.for_tenant)."""
    if not admin.is_super:
        raise HTTPException(
            status_code=403, detail="Только супер-админ может менять настройки Green API"
        )
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    from app.services.whatsapp_service import WhatsAppService

    wa = WhatsAppService.for_tenant(tenant, trc)
    ok = await run_in_threadpool(wa.set_send_delay, data.delay_ms, data.webhook_url)
    logger.info(
        "Green API pacing set by %s tenant=%s delay_ms=%s webhook=%s ok=%s",
        admin.username, tenant_id, data.delay_ms, bool(data.webhook_url), ok,
    )
    return GreenApiPacingResponse(
        success=ok, id_instance=wa.id_instance, delay_ms=data.delay_ms,
        webhook_configured=ok and bool(data.webhook_url),
    )


def _looks_like_sendable_phone(phone: str) -> bool:
    """Реальный кейс 2026-09-09: 2 из 104 "зависших" номеров в исходных
    данных оказались мусором вида "116" — не настоящий номер, а какой-то
    сбой при экспорте/матчинге. Без этой проверки такой "номер" ушёл бы в
    Green API как есть (send_message нормализует и попытается отправить
    что попало) и просто зря сжёг бы отправку из дневного лимита."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return 10 <= len(digits) <= 15


@router.post(
    "/trcs/{trc_id}/resend-by-invoice",
    response_model=ResendByInvoiceResponse,
)
async def resend_by_invoice(
    trc_id: int,
    data: ResendByInvoiceRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Точечная пересылка по явному списку (телефон, invoice_id) — не общий
    "переслать всё FAILED", потому что записи от инцидента 2026-09-09 в БД
    уже стоят DELIVERED (проставлено оптимистично до фикса от 2026-09-10,
    см. whatsapp_jobs.deliver_notification) — обычный поиск по статусу их
    не найдёт. Список сверен напрямую с Green API GetChatHistory, а не с
    нашей БД (см. scripts/maxi_mall_2026_09_09_stuck_messages.json).

    Каждый элемент создаёт НОВУЮ Notification-строку (не трогает старую
    неверную запись — она остаётся историческим свидетельством инцидента) и
    ставит её в ту же Kafka-очередь whatsapp_send, что и обычная отправка —
    это значит, что она автоматически идёт под тем же pacing
    (kafka_worker._paced_sleep) и дневным лимитом (_effective_daily_send_count),
    что и любая другая отправка, а не мгновенным циклом в этом запросе,
    который бы повторил ровно тот же инцидент ещё раз."""
    if not admin.is_super:
        raise HTTPException(
            status_code=403, detail="Только супер-админ может пересылать WhatsApp вручную"
        )
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")

    service = NotificationService(db)
    results: List[ResendByInvoiceItemResult] = []
    queued = 0

    for item in data.items:
        if not _looks_like_sendable_phone(item.phone):
            results.append(ResendByInvoiceItemResult(
                phone=item.phone, invoice_id=item.invoice_id, outcome="invalid_phone",
            ))
            continue

        payment = (
            db.query(TenantPayment)
            .join(Tenant, Tenant.id == TenantPayment.tenant_id)
            .filter(Tenant.trc_id == trc_id, TenantPayment.invoice_id == item.invoice_id)
            .first()
        )
        if not payment:
            results.append(ResendByInvoiceItemResult(
                phone=item.phone, invoice_id=item.invoice_id, outcome="invoice_not_found",
            ))
            continue

        # Уже реально подтверждено вебхуком — пересылать нечего, случайный
        # повторный вызов этого эндпоинта не должен дублировать уже дошедшие
        # сообщения. ВАЖНО: ни status == DELIVERED, ни delivered_at IS NOT
        # NULL сами по себе не доказывают это — старый код (ДО фикса от
        # 2026-09-10, см. app.models.notification.Notification.delivered_at)
        # синхронно проставлял ОБА поля сразу по HTTP 200 от sendMessage, то
        # есть у всех строк инцидента 2026-09-09 (ради которых этот эндпоинт
        # и написан) delivered_at тоже заполнен — просто он врёт. Живая
        # проверка 2026-09-10: для notification_id=7411 (invoice
        # 9c1ba2e1-ab48..., delivered_at=2026-09-09T07:43:18) прямой запрос
        # к Green API GetChatHistory показал реальный statusMessage="sent" —
        # WhatsApp это сообщение не доставил, несмотря на "подтверждённый"
        # delivered_at в нашей БД.
        #
        # Единственное поле, которое старый код НИКОГДА не трогал —
        # green_api_id_message (столбец и его единственное присвоение
        # добавлены тем же фиксом от 2026-09-10, никакого backfill для
        # старых строк не было и не будет) — а DELIVERED сейчас выставляется
        # только в _process_green_api_webhook, которая находит нужную
        # Notification именно по green_api_id_message. Значит
        # status == DELIVERED вместе с непустым green_api_id_message может
        # появиться только через настоящее вебхук-подтверждение.
        already_delivered = (
            db.query(Notification)
            .filter(
                Notification.payment_id == payment.id,
                Notification.status == NotificationStatus.DELIVERED,
                Notification.green_api_id_message.isnot(None),
            )
            .first()
        )
        if already_delivered:
            results.append(ResendByInvoiceItemResult(
                phone=item.phone, invoice_id=item.invoice_id, outcome="already_delivered",
            ))
            continue

        prior = service.get_notifications_by_payment(payment.id)
        notification_type = prior[0].notification_type if prior else NotificationType.OVERDUE

        notification, _queued_ok = await run_in_threadpool(
            service.send_notification,
            NotificationSend(
                payment_id=payment.id,
                notification_type=notification_type,
                phone_number=item.phone,
                counterparty_id=payment.counterparty_id,
                invoice_id=payment.invoice_id,
                service_type=payment.service_type,
            ),
            file_path=None,
            tenant_id=payment.tenant_id,
            counterparty_name=payment.tenant_name,
            immediate=False,
            defer_whatsapp=False,
        )
        queued += 1
        results.append(ResendByInvoiceItemResult(
            phone=item.phone, invoice_id=item.invoice_id,
            outcome="queued", notification_id=notification.id,
        ))

    logger.info(
        "Manual resend-by-invoice by %s trc=%s: queued=%s skipped=%s total=%s",
        admin.username, trc_id, queued, len(results) - queued, len(data.items),
    )
    return ResendByInvoiceResponse(
        queued=queued, skipped=len(results) - queued, results=results,
    )


@router.get(
    "/trcs/{trc_id}/counterparty-phones",
    response_model=List[CounterpartyPhoneResponse],
)
async def list_counterparty_phones(
    trc_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")
    rows = (
        db.query(CounterpartyPhone)
        .filter(CounterpartyPhone.trc_id == trc_id)
        .order_by(CounterpartyPhone.counterparty_name)
        .all()
    )
    return rows


@router.put(
    "/trcs/{trc_id}/counterparty-phones",
    response_model=List[CounterpartyPhoneResponse],
)
async def upsert_counterparty_phones(
    trc_id: int,
    items: List[CounterpartyPhoneUpsert],
    tenant_id: Optional[int] = Query(
        None,
        description="Арендатор для записи телефона в 1С (OData того же инстанса)",
    ),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Сохранить телефоны получателей для рассылки (по ID контрагента из 1С)."""
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")

    existing = {
        row.one_c_counterparty_id.lower(): row
        for row in db.query(CounterpartyPhone).filter(CounterpartyPhone.trc_id == trc_id).all()
    }
    saved: List[CounterpartyPhone] = []
    for item in items:
        phone = (item.phone or "").strip()
        if not phone:
            continue
        cp_id = item.one_c_counterparty_id.strip()
        key = cp_id.lower()
        row = existing.get(key)
        if row:
            row.phone = phone
            row.counterparty_name = item.counterparty_name or row.counterparty_name
            row.contact_name = item.contact_name or row.contact_name
        else:
            row = CounterpartyPhone(
                trc_id=trc_id,
                one_c_counterparty_id=cp_id,
                counterparty_name=item.counterparty_name,
                contact_name=item.contact_name,
                phone=phone,
            )
            db.add(row)
            existing[key] = row
        saved.append(row)
    db.commit()
    for row in saved:
        db.refresh(row)

    tenant = (
        db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.trc_id == trc_id).first()
        if tenant_id
        else _first_tenant_for_trc(db, trc_id)
    )
    if tenant:
        from app.services.counterparty_contact_sync import (
            refresh_counterparties_after_phone_write,
            sync_counterparty_phone_field_to_1c,
        )
        from app.services.tenant_1c import get_integration_for_tenant

        integration = get_integration_for_tenant(db, tenant.id)

        def _sync_all_to_1c() -> tuple[bool, list[str]]:
            any_ok = False
            failed: list[str] = []
            for item in items:
                phone_field = (item.phone or "").strip()
                if not phone_field:
                    continue
                sync_result = sync_counterparty_phone_field_to_1c(
                    integration,
                    item.one_c_counterparty_id.strip(),
                    phone_field,
                )
                if sync_result.get("supported") and sync_result.get("ok"):
                    any_ok = True
                elif sync_result.get("supported") and not sync_result.get("ok"):
                    failed.extend(sync_result.get("messages") or [])
            return any_ok, failed

        try:
            # Синхронные HTTP-запросы к 1С, один на элемент — без threadpool
            # подвешивает единственный uvicorn-воркер (см. аудит от 2026-08-25).
            any_supported_ok, failed_messages = await run_in_threadpool(_sync_all_to_1c)
        finally:
            if hasattr(integration, "close"):
                try:
                    integration.close()
                except Exception:
                    pass

        if failed_messages:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Телефоны сохранены на платформе, но часть не записалась в 1С: "
                    + "; ".join(failed_messages[:10])
                ),
            )
        if any_supported_ok:
            refresh_counterparties_after_phone_write(db, tenant.id)

    return saved


@router.post(
    "/trcs/{trc_id}/counterparty-phones/sync-to-1c",
    response_model=CounterpartyPhoneBackfillResponse,
)
async def sync_counterparty_phones_to_1c_backfill(
    trc_id: int,
    tenant_id: int = Query(
        ...,
        description="ID арендатора City Mall (Nova OData / прямой OData). COM Maxi не поддерживается.",
    ),
    dry_run: bool = Query(
        False,
        description="true — только показать, что будет отправлено, без записи в 1С",
    ),
    limit: int = Query(
        0,
        ge=0,
        description="Размер пачки (0 = все). На проде из-за timeout берите 20–50.",
    ),
    after_id: int = Query(
        0,
        ge=0,
        description="Продолжить после id записи counterparty_phones (из last_processed_id).",
    ),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """
    Backfill: телефоны из counterparty_phones → 1С (Nova OData contacts_set / прямой OData),
    затем sync кэша контрагентов.

    Вызывается из Swagger/admin без доступа к поду.
    На проде запускайте пачками: limit=20&after_id=<last_processed_id>.
    """
    trc = db.query(TRC).filter(TRC.id == trc_id).first()
    if not trc:
        raise HTTPException(status_code=404, detail="ТРЦ не найден")

    from app.services.counterparty_phone_backfill import backfill_counterparty_phones_to_1c

    # Пачка синхронных HTTP-запросов к 1С — без threadpool подвешивает
    # единственный uvicorn-воркер на всё время бэкфилла (см. аудит от 2026-08-25).
    result = await run_in_threadpool(
        backfill_counterparty_phones_to_1c,
        db,
        tenant_id=tenant_id,
        trc_id=trc_id,
        dry_run=dry_run,
        limit=limit,
        after_id=after_id,
    )
    if result.get("error") and result.get("total", 0) == 0 and not result.get("ok"):
        # Конфиг/валидация (нет tenant, Nova, нет клиента) — клиентская/бизнес-ошибка
        status_code = 400
        err = str(result.get("error") or "")
        if "не найден" in err:
            status_code = 404
        elif "недоступен" in err:
            status_code = 502
        raise HTTPException(status_code=status_code, detail=err)
    return result


@router.delete("/trcs/{trc_id}/counterparty-phones/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_counterparty_phone(
    trc_id: int,
    phone_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    row = (
        db.query(CounterpartyPhone)
        .filter(CounterpartyPhone.id == phone_id, CounterpartyPhone.trc_id == trc_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(row)
    db.commit()


@router.post(
    "/auto-notifications/run",
    response_model=AutoNotificationRunResponse,
)
async def run_auto_notifications(
    data: AutoNotificationRunRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    if not admin.is_super:
        raise HTTPException(
            status_code=403,
            detail="Только супер-админ может запускать авторассылку",
        )
    from app.services.auto_notification_service import (
        AutoNotificationService,
        in_sending_window,
    )

    can_send = True if data.force_window else in_sending_window()
    svc = AutoNotificationService(db)

    def _run_sync() -> int:
        if data.tenant_id:
            return svc.run_for_tenant(data.tenant_id, can_send=can_send)
        if data.force_window:
            total = 0
            from app.models.catalog import Tenant
            from app.services.tenant_1c import tenant_has_1c_credentials

            tenants = (
                db.query(Tenant)
                .filter(Tenant.is_active.is_(True))
                .filter(Tenant.green_api_id_instance.isnot(None))
                .filter(Tenant.green_api_api_token.isnot(None))
                .all()
            )
            for tenant in tenants:
                if not tenant_has_1c_credentials(tenant):
                    continue
                try:
                    total += svc.run_for_tenant(tenant.id, can_send=True)
                except Exception as exc:
                    logger.exception(
                        "Manual auto notify failed tenant=%s: %s", tenant.id, exc
                    )
            return total
        return svc.run_for_all_tenants()

    # Может пройтись по 1С (до 50000 счетов на арендатора) и Green API для
    # многих арендаторов подряд — не первый раз в event loop единственного
    # uvicorn-воркера, иначе одна ручная авторассылка подвешивает весь backend.
    sent = await run_in_threadpool(_run_sync)
    logger.info(
        "Manual auto notify by %s tenant=%s sent=%s can_send=%s force=%s",
        admin.username,
        data.tenant_id,
        sent,
        can_send,
        data.force_window,
    )
    return AutoNotificationRunResponse(
        sent=sent,
        can_send=can_send,
        tenant_id=data.tenant_id,
    )


# TODO(dev-only): служебный эндпоинт форс-рефреша PDF в обход 7-дневного кэша
# (nova_buh_1c_client._PDF_CACHE_MAX_AGE). Нужен только на время активной разработки
# макета счёта — убрать вместе с этим комментарием, когда вёрстка стабилизируется.
@router.post("/invoices/{invoice_id}/refresh-pdf")
async def refresh_invoice_pdf(
    invoice_id: str,
    tenant_id: int = Query(..., description="ID тенанта, к которому относится счёт"),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    if not admin.is_super:
        raise HTTPException(
            status_code=403,
            detail="Только супер-админ может форсировать пересборку PDF",
        )

    from app.client_1c.exceptions import MissingSupplierRequisitesError, ValidationError
    from app.services.nova_1c_service import Nova1CServiceError
    from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id

    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Тенант не найден")

    integration = get_integration_for_tenant(db, tenant_id)
    if not integration.client:
        raise HTTPException(status_code=503, detail="1C client not available")

    if not integration.client.access_token:
        try:
            integration.client.authenticate()
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}")

    # Троттлинг живёт здесь, не в клиентах download_invoice_file — тот же
    # раздел ответственности, что уже у admin.is_super чуть выше ("можно ли
    # вообще force-refresh") и не у клиента ("как достать PDF"). Без этого
    # force-refresh сам стал бы готовым способом воспроизвести Nova
    # 502-шторм 2026-08-25/26, от которого кэш и защищает — см.
    # app/services/invoice_pdf_cache.py. Внутри try/except ValidationError —
    # can_attempt_force_refresh тоже гоняет invoice_id через ту же
    # GUID-валидацию, что и download_invoice_file ниже.
    from app.services.invoice_pdf_cache import (
        FORCE_REFRESH_COOLDOWN,
        can_attempt_force_refresh,
        mark_force_refresh_attempted,
    )

    try:
        if not can_attempt_force_refresh(db, tenant_id, invoice_id):
            cooldown_min = int(FORCE_REFRESH_COOLDOWN.total_seconds() // 60)
            raise HTTPException(
                status_code=429,
                detail=f"Force-refresh для этого счёта уже запускали недавно — подождите {cooldown_min} мин.",
            )
        mark_force_refresh_attempted(db, tenant_id, invoice_id)

        file_path = integration.download_invoice_file(invoice_id, tenant=tenant, force=True)
    except ValidationError as exc:
        # e.g. invoice_id isn't a valid GUID — reject before it reaches 1C
        # rather than 500ing (see _guid_literal, audit from 2026-08-25).
        raise HTTPException(status_code=400, detail=str(exc))
    except MissingSupplierRequisitesError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Nova1CServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not file_path or not Path(file_path).is_file():
        raise HTTPException(status_code=404, detail="PDF не удалось сформировать")

    logger.warning(
        "[force-refresh-pdf] admin=%s invoice_id=%s tenant_id=%s regenerated %s",
        admin.username,
        invoice_id,
        tenant_id,
        file_path,
    )

    file_content = Path(file_path).read_bytes()
    return Response(
        content=file_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{invoice_id}.pdf"},
    )


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    data: AdminUserCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    if not admin.is_super:
        raise HTTPException(status_code=403, detail="Только супер-админ может создавать пользователей")
    exists = db.query(AdminUser).filter(AdminUser.username == data.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    user = AdminUser(
        username=data.username,
        password_hash=hash_password(data.password),
        is_super=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
