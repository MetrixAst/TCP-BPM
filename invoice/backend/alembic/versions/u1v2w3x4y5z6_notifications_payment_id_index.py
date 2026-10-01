"""индекс notifications.payment_id — реестр платежей больше не делает N+1 без него

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-08-03

GET /api/payments теперь берёт уведомления одним batched IN(...)-запросом
вместо запроса на каждую строку страницы (см. app/api/payments.py), но без
индекса на payment_id этот единственный запрос всё равно был бы seq scan
по notifications при росте таблицы.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    try:
        return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _has_index(inspector, "notifications", "ix_notifications_payment_id"):
        op.create_index(
            op.f("ix_notifications_payment_id"),
            "notifications",
            ["payment_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_index(inspector, "notifications", "ix_notifications_payment_id"):
        op.drop_index(op.f("ix_notifications_payment_id"), table_name="notifications")
