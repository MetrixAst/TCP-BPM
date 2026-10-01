"""пауза авто-рассылки на уровне арендатора (все контрагенты)

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-09-08

tenants.auto_notify_paused — кнопка «Отключить авто-напоминания для всех» в
invoice-client, останавливает AutoNotificationService.run_for_tenant целиком
для арендатора, независимо от точечных CounterpartyPhone.auto_notify_paused
(см. u2v3w4x5y6z7). server_default=false — поведение не меняется ни для
одного существующего арендатора.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "v3w4x5y6z7a8"
down_revision: Union[str, None] = "u2v3w4x5y6z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    try:
        return any(col["name"] == column_name for col in inspector.get_columns(table_name))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _has_column(inspector, "tenants", "auto_notify_paused"):
        op.add_column(
            "tenants",
            sa.Column(
                "auto_notify_paused",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_column(inspector, "tenants", "auto_notify_paused"):
        op.drop_column("tenants", "auto_notify_paused")
