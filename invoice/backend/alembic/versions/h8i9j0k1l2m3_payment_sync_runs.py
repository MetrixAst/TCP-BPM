"""payment_sync_runs for background 1C sync status

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import table_exists

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("payment_sync_runs"):
        return
    op.create_table(
        "payment_sync_runs",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("records", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "period"),
    )
    op.create_index(
        "ix_payment_sync_runs_status",
        "payment_sync_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    if table_exists("payment_sync_runs"):
        op.drop_index("ix_payment_sync_runs_status", table_name="payment_sync_runs")
        op.drop_table("payment_sync_runs")
