"""counterparty phone routing + auto notification log

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing, table_exists

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "counterparty_phones",
        sa.Column("phone_rent", sa.String(length=32), nullable=True),
    )
    add_column_if_missing(
        "counterparty_phones",
        sa.Column("phone_utilities", sa.String(length=32), nullable=True),
    )
    if not table_exists("auto_notification_logs"):
        op.create_table(
            "auto_notification_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("counterparty_id", sa.String(length=64), nullable=False),
            sa.Column("invoice_id", sa.String(length=64), nullable=False),
            sa.Column("service_type", sa.String(length=16), nullable=False),
            sa.Column("trigger_kind", sa.String(length=32), nullable=False),
            sa.Column("phone_number", sa.String(length=32), nullable=True),
            sa.Column(
                "sent_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "invoice_id",
                "service_type",
                "trigger_kind",
                name="uq_auto_notify_once",
            ),
        )
        op.create_index(
            "ix_auto_notification_logs_tenant_id",
            "auto_notification_logs",
            ["tenant_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_auto_notification_logs_tenant_id", table_name="auto_notification_logs")
    op.drop_table("auto_notification_logs")
    op.drop_column("counterparty_phones", "phone_utilities")
    op.drop_column("counterparty_phones", "phone_rent")
