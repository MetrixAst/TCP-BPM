"""пауза авто-рассылки на уровне контрагента

Revision ID: u2v3w4x5y6z7
Revises: t8u9v0w1x2y3
Create Date: 2026-09-08

counterparty_phones.auto_notify_paused — арендатор ставит авто-рассылку
(AutoNotificationService) на паузу для одного контрагента из invoice-client;
ручную отправку и массовую /send-debtors не затрагивает. server_default=false
— поведение не меняется ни для одного существующего контрагента.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, None] = "t8u9v0w1x2y3"
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
    if not _has_column(inspector, "counterparty_phones", "auto_notify_paused"):
        op.add_column(
            "counterparty_phones",
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
    if _has_column(inspector, "counterparty_phones", "auto_notify_paused"):
        op.drop_column("counterparty_phones", "auto_notify_paused")
