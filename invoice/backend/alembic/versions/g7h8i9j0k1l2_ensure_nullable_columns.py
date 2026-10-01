"""idempotent ensure nullable columns (safe prod redeploy)

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-04

Повторно проверяет опциональные колонки и таблицы: если уже есть — пропуск.
Не трогает данные в строках (только NULLable поля).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing, table_exists

revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        sa.Column("stamp_file_path", sa.String(length=512), nullable=True),
        sa.Column("signature_file_path", sa.String(length=512), nullable=True),
        sa.Column("invoice_iik", sa.String(length=34), nullable=True),
        sa.Column("invoice_kbe", sa.String(length=8), nullable=True),
        sa.Column("invoice_bank_name", sa.String(length=255), nullable=True),
        sa.Column("invoice_bank_bik", sa.String(length=16), nullable=True),
        sa.Column("invoice_payment_knp", sa.String(length=16), nullable=True),
        sa.Column("invoice_supplier_address", sa.Text(), nullable=True),
        sa.Column("invoice_executor_name", sa.String(length=128), nullable=True),
        sa.Column("invoice_contract_text", sa.String(length=255), nullable=True),
        sa.Column("invoice_due_day", sa.Integer(), nullable=True),
        sa.Column("invoice_due_day_utilities", sa.Integer(), nullable=True),
    ):
        add_column_if_missing("tenants", col)

    for col in (
        sa.Column("phone_rent", sa.String(length=32), nullable=True),
        sa.Column("phone_utilities", sa.String(length=32), nullable=True),
    ):
        add_column_if_missing("counterparty_phones", col)

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
