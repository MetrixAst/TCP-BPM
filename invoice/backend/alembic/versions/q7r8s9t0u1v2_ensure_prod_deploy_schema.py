"""idempotent ensure schema for prod deploy (Nova org, cache, payments)

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-06-25

Повторно проверяет объекты последних релизов: если уже есть — пропуск.
Безопасно для prod, где часть миграций могла не примениться или create_all опередил alembic.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing, table_exists

revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        sa.Column("nova_organization_id", sa.Integer(), nullable=True),
        sa.Column("one_c_connection_mode", sa.String(length=32), nullable=True),
        sa.Column("invoice_due_day_operations", sa.Integer(), nullable=True),
        sa.Column("payment_rent_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("payment_utilities_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("payment_operations_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("payment_keywords_rent", sa.Text(), nullable=True),
        sa.Column("payment_keywords_utilities", sa.Text(), nullable=True),
        sa.Column("payment_keywords_operations", sa.Text(), nullable=True),
    ):
        add_column_if_missing("tenants", col)

    for col in (
        sa.Column("phone_operations", sa.String(length=32), nullable=True),
    ):
        add_column_if_missing("counterparty_phones", col)

    if not table_exists("counterparty_cache"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS counterparty_cache (
                tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                data JSONB,
                total_from_1c INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'idle',
                error TEXT,
                started_at TIMESTAMPTZ,
                synced_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_counterparty_cache_status
            ON counterparty_cache (status)
            """
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
    pass
