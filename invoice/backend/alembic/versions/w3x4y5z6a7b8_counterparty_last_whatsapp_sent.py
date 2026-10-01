"""дата последнего WhatsApp-напоминания на уровне контрагента

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-08-03

counterparty_phones.last_whatsapp_sent_at — обновляется при любой успешной
отправке (ручной /send, массовой /send-debtors, авто-рассылке, /send-file),
см. app/services/whatsapp_jobs.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "v2w3x4y5z6a7"
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
    if not _has_column(inspector, "counterparty_phones", "last_whatsapp_sent_at"):
        op.add_column(
            "counterparty_phones",
            sa.Column("last_whatsapp_sent_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_column(inspector, "counterparty_phones", "last_whatsapp_sent_at"):
        op.drop_column("counterparty_phones", "last_whatsapp_sent_at")
