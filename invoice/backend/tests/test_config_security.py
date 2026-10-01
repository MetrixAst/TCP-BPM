import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models.catalog import AdminUser
from app.services import catalog_seed

PG_URL = "postgresql+psycopg://u:p@127.0.0.1:9/db"


@pytest.mark.parametrize(
    "secret_key",
    ["dev-secret-key-change-in-production", "change-me-long-random-string", "short"],
)
def test_production_rejects_weak_secret_key(secret_key):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(ENVIRONMENT="production", SECRET_KEY=secret_key, DATABASE_URL=PG_URL)


def test_production_accepts_strong_secret_key():
    s = Settings(ENVIRONMENT="production", SECRET_KEY="x" * 40, DATABASE_URL=PG_URL)
    assert s.SECRET_KEY == "x" * 40


def test_non_production_allows_default_secret_key():
    s = Settings(
        ENVIRONMENT="test",
        SECRET_KEY="dev-secret-key-change-in-production",
        DATABASE_URL=PG_URL,
    )
    assert s.ENVIRONMENT == "test"


def test_env_file_with_upload_dirs_is_valid(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        f"DATABASE_URL={PG_URL}\n"
        "TENANT_UPLOADS_DIR=/app/uploads/tenants\n"
        "WHATSAPP_OUTBOX_DIR=/app/uploads/outbox\n"
    )
    s = Settings(_env_file=str(env))
    assert s.TENANT_UPLOADS_DIR == "/app/uploads/tenants"


def test_super_admin_not_created_without_password(db_session, monkeypatch):
    monkeypatch.setattr(catalog_seed.settings, "SUPER_ADMIN_PASSWORD", "")
    catalog_seed.ensure_super_admin(db_session)
    assert db_session.query(AdminUser).count() == 0


def test_super_admin_created_with_password(db_session, monkeypatch):
    monkeypatch.setattr(catalog_seed.settings, "SUPER_ADMIN_PASSWORD", "s3cret-pass")
    catalog_seed.ensure_super_admin(db_session)
    admin = db_session.query(AdminUser).one()
    assert admin.is_super
