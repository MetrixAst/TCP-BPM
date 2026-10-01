"""Идемпотентные DDL-дополнения на старте (если alembic не догнал prod)."""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Колонки SMTP для рассылок — без них любой SELECT из Tenant даёт 500.
_TENANT_SMTP_COLUMNS_SQL = (
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_host VARCHAR(255)",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_port INTEGER",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_use_starttls "
    "BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_username VARCHAR(255)",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_password VARCHAR(255)",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_from_email VARCHAR(255)",
)


def ensure_tenant_smtp_columns(engine: Engine) -> None:
    """Добавляет smtp_* в tenants, если их ещё нет (Postgres)."""
    with engine.begin() as conn:
        for stmt in _TENANT_SMTP_COLUMNS_SQL:
            conn.execute(text(stmt))
    logger.info("Tenant SMTP columns ensured")
