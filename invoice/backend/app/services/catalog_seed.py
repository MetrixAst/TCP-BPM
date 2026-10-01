from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.catalog import AdminUser, Tenant


def ensure_super_admin(db: Session) -> None:
    if not settings.SUPER_ADMIN_PASSWORD:
        return
    existing = (
        db.query(AdminUser)
        .filter(AdminUser.username == settings.SUPER_ADMIN_USERNAME)
        .first()
    )
    if existing:
        return
    admin = AdminUser(
        username=settings.SUPER_ADMIN_USERNAME,
        password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
        is_super=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()


def sync_tenant_green_api_from_env(db: Session) -> None:
    """Переносит GREEN_API_* из .env в арендатора ИП MOON (если заданы)."""
    if not settings.GREEN_API_ID_INSTANCE and not settings.GREEN_API_API_TOKEN:
        return
    tenant = db.query(Tenant).filter(Tenant.id == 1).first()
    if not tenant:
        return
    tenant.green_api_url = settings.GREEN_API_URL or tenant.green_api_url
    tenant.green_api_media_url = settings.GREEN_API_MEDIA_URL or tenant.green_api_media_url
    if settings.GREEN_API_ID_INSTANCE:
        tenant.green_api_id_instance = settings.GREEN_API_ID_INSTANCE
    if settings.GREEN_API_API_TOKEN:
        tenant.green_api_api_token = settings.GREEN_API_API_TOKEN
    db.commit()
