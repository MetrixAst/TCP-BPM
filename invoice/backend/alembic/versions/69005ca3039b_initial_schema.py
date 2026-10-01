"""initial_schema

Revision ID: 69005ca3039b
Revises:
Create Date: 2026-05-23 14:28:30.893696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

import app.models.catalog  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.payment  # noqa: F401
from app.db.database import Base

revision: str = "69005ca3039b"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("trcs"):
        Base.metadata.create_all(bind=bind)
        return

    if not _has_index(inspector, "tenant_payments", "ix_tenant_payments_counterparty_id"):
        op.create_index(
            op.f("ix_tenant_payments_counterparty_id"),
            "tenant_payments",
            ["counterparty_id"],
            unique=False,
        )
    if not _has_index(inspector, "tenants", "ix_tenants_portal_username"):
        op.create_index(
            op.f("ix_tenants_portal_username"),
            "tenants",
            ["portal_username"],
            unique=True,
        )


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    try:
        return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))
    except Exception:
        return False


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("trcs"):
        if _has_index(inspector, "tenants", "ix_tenants_portal_username"):
            op.drop_index(op.f("ix_tenants_portal_username"), table_name="tenants")
        if _has_index(inspector, "tenant_payments", "ix_tenant_payments_counterparty_id"):
            op.drop_index(
                op.f("ix_tenant_payments_counterparty_id"),
                table_name="tenant_payments",
            )
