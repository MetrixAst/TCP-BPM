
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import security_scheme
from app.core.security import decode_access_token, decode_tenant_portal_token
from app.db.database import get_db
from app.models.catalog import AdminUser, Tenant


def _bearer_token(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if credentials and credentials.credentials:
        return credentials.credentials
    return None


def get_portal_tenant_ids(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[dict]:
    token = _bearer_token(credentials)
    if not token:
        return None
    return decode_tenant_portal_token(token)


def _is_authorized_admin(
    db: Session,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> bool:
    """Админский JWT (тот же, что для /api/admin/*) — доступ для сотрудников MetriX."""
    token = _bearer_token(credentials)
    if not token:
        return False
    username = decode_access_token(token)
    if not username:
        return False
    return (
        db.query(AdminUser)
        .filter(AdminUser.username == username, AdminUser.is_active.is_(True))
        .first()
        is not None
    )


def resolve_tenant_id(
    db: Session,
    requested_tenant_id: Optional[int],
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[int]:
    """
    JWT арендатора — всегда его tenant_id.
    JWT ТРЦ — tenant_id из query, если арендатор принадлежит этому ТРЦ.
    Admin JWT — tenant_id из query, как есть (тот же уровень доступа, что и /api/admin/*).
    Без валидного токена — 401: анонимный доступ по голому tenant_id закрыт (CVE-подобный IDOR).
    """
    portal = get_portal_tenant_ids(credentials)
    if portal:
        if portal.get("role") == "trc":
            if requested_tenant_id:
                tenant = (
                    db.query(Tenant)
                    .filter(
                        Tenant.id == requested_tenant_id,
                        Tenant.trc_id == portal["trc_id"],
                        Tenant.is_active.is_(True),
                    )
                    .first()
                )
                if not tenant:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Арендатор не входит в ваш ТРЦ",
                    )
                return requested_tenant_id
            # Без явного tenant_id раньше отдавали None, а None ниже по цепочке
            # (PaymentService._apply_payment_filters и все остальные потребители
            # scoped_tenant_id) означает "без ограничения по арендатору" — тот же
            # смысл, что и для админского JWT. Для роли ТРЦ это давало доступ ко
            # ВСЕМ арендаторам ВСЕХ ТРЦ в системе (не только своим), т.к. другого
            # фильтра (ip_name/tenant_name) фронт для роли trc тоже не шлёт.
            # Резолвим в единственного активного арендатора своего ТРЦ — сегодня
            # у каждого ТРЦ ровно один Tenant, так что для существующих логинов
            # это ничего не меняет в UX, просто убирает дыру. Если у ТРЦ появится
            # несколько арендаторов — до появления в UI выбора конкретного
            # арендатора безопаснее явно потребовать tenant_id, чем угадывать.
            own_tenant_ids = [
                t.id
                for t in db.query(Tenant.id)
                .filter(Tenant.trc_id == portal["trc_id"], Tenant.is_active.is_(True))
                .all()
            ]
            if len(own_tenant_ids) == 1:
                return own_tenant_ids[0]
            if not own_tenant_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="У вашего ТРЦ нет активных арендаторов",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У вашего ТРЦ несколько арендаторов — укажите tenant_id",
            )
        locked_id = portal["tenant_id"]
        if not locked_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Арендатор не найден",
            )
        if requested_tenant_id and int(requested_tenant_id) != locked_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ только к данным вашего арендатора",
            )
        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == locked_id, Tenant.is_active.is_(True))
            .first()
        )
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Арендатор не найден или отключён",
            )
        return locked_id

    if _is_authorized_admin(db, credentials):
        return requested_tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется авторизация (вход арендатора/ТРЦ или администратора)",
    )


def scoped_tenant_id(
    tenant_id: Optional[int] = Query(None, description="Catalog tenant ID"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Optional[int]:
    return resolve_tenant_id(db, tenant_id, credentials)
