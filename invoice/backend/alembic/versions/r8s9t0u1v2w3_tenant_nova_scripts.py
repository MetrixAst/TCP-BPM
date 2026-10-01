"""tenant nova mcp script ids

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        sa.Column("nova_mcp_system_type", sa.String(length=16), nullable=True),
        sa.Column("nova_script_invoices", sa.Integer(), nullable=True),
        sa.Column("nova_script_payments", sa.Integer(), nullable=True),
        sa.Column("nova_script_counterparties", sa.Integer(), nullable=True),
        sa.Column("nova_script_balance", sa.Integer(), nullable=True),
        sa.Column("nova_script_invoice_by_id", sa.Integer(), nullable=True),
    ):
        add_column_if_missing("tenants", col)


def downgrade() -> None:
    op.drop_column("tenants", "nova_script_invoice_by_id")
    op.drop_column("tenants", "nova_script_balance")
    op.drop_column("tenants", "nova_script_counterparties")
    op.drop_column("tenants", "nova_script_payments")
    op.drop_column("tenants", "nova_script_invoices")
    op.drop_column("tenants", "nova_mcp_system_type")
