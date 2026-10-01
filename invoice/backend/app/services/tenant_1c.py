"""Resolve tenant 1C connection mode and build Integration1C."""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalog import Tenant
from app.services.integration_1c import Integration1C
from app.services.nova_script_defaults import tenant_nova_script_mapping
from app.services.odata_1c_client import is_odata_url

CONNECTION_MODE_AUTO = "auto"
CONNECTION_MODE_ODATA = "odata_direct"
CONNECTION_MODE_NOVA = "nova_org"


def get_tenant_by_id(db: Session, tenant_id: Optional[int]) -> Optional[Tenant]:
    if not tenant_id:
        return None
    return (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.is_active.is_(True))
        .first()
    )


def tenant_uses_nova_org(tenant: Optional[Tenant]) -> bool:
    if not tenant or not tenant.nova_organization_id:
        return False
    mode = (tenant.one_c_connection_mode or CONNECTION_MODE_AUTO).strip().lower()
    if mode == CONNECTION_MODE_ODATA:
        return False
    if mode == CONNECTION_MODE_NOVA:
        return True
    # auto: OData только если заданы URL + логин (как CityMall org 118).
    # Иначе COM/MCP по nova_organization_id (Maxi Mall org 119).
    login = (tenant.one_c_login or "").strip()
    base_url = (tenant.one_c_base_url or settings.ONE_C_BASE_URL or "").strip()
    if login and base_url and is_odata_url(base_url):
        return False
    return True


def tenant_has_1c_credentials(tenant: Optional[Tenant]) -> bool:
    if not tenant:
        return False
    if tenant_uses_nova_org(tenant):
        return True
    login = (tenant.one_c_login or "").strip()
    password = (tenant.one_c_password or "").strip()
    return bool(login and password)


def build_integration_for_tenant(tenant: Optional[Tenant]) -> Integration1C:
    if not tenant:
        integration = Integration1C()
        if not integration.client:
            integration.last_error = integration.last_error or "Арендатор не выбран"
        return integration

    mode = (tenant.one_c_connection_mode or CONNECTION_MODE_AUTO).strip().lower()
    if mode == CONNECTION_MODE_NOVA and not tenant.nova_organization_id:
        import logging

        logging.getLogger(__name__).warning(
            "Tenant id=%s mode=nova_org but nova_organization_id is empty — "
            "счета могут не совпадать с Postman/Nova. Укажите org_id ",
            tenant.id,
        )

    if tenant_uses_nova_org(tenant):
        integration = Integration1C(
            one_c_config={
                "nova_organization_id": tenant.nova_organization_id,
                "nova_script_ids": tenant_nova_script_mapping(tenant),
            }
        )
    elif not (tenant.one_c_login or "").strip() or not (tenant.one_c_password or "").strip():
        integration = Integration1C()
        integration.client = None
        integration.last_error = (
            "Для арендатора не задан логин или пароль 1С. "
            "В админке укажите one_c_login и пароль 1С (пустое поле пароля не сохраняет старый — введите заново), "
            "либо задайте Nova org_id для подключения через MCP."
        )
        return integration
    elif not (tenant.one_c_base_url or "").strip():
        # Раньше здесь молча подставлялся settings.ONE_C_BASE_URL — общий
        # заглушечный адрес, не принадлежащий ни одному реальному арендатору.
        # Итог: запрос "успешно" уходил не туда и тихо возвращал 0 записей
        # (инцидент ИП MOON, 2026-08-11 — tenant_id=4 сутками синкался в
        # supersecret.irm.kz вместо своего Nova org 127). Явная ошибка вместо
        # тихого фолбэка — единственный способ это заметить раньше клиента.
        integration = Integration1C()
        integration.client = None
        integration.last_error = (
            "Для арендатора выбран режим odata_direct, но one_c_base_url не задан. "
            "Укажите адрес OData-сервера в админке, либо переключите режим на nova_org "
            "и задайте Nova org_id для подключения через MCP."
        )
        return integration
    else:
        integration = Integration1C(
            one_c_config={
                "base_url": tenant.one_c_base_url,
                "basic_auth_user": tenant.one_c_basic_user or settings.ONE_C_BASIC_AUTH_USER,
                "basic_auth_password": tenant.one_c_basic_password
                or settings.ONE_C_BASIC_AUTH_PASSWORD,
                "api_user": (tenant.one_c_login or "").strip(),
                "api_password": tenant.one_c_password or "",
            }
        )

    integration.pdf_tenant = tenant
    return integration


def get_integration_for_tenant(db: Session, tenant_id: Optional[int]) -> Integration1C:
    tenant = get_tenant_by_id(db, tenant_id)
    return build_integration_for_tenant(tenant)
