"""tenant due day operations + phone_operations

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7r8
Create Date: 2026-06-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "tenants",
        sa.Column("invoice_due_day_operations", sa.Integer(), nullable=True),
    )
    add_column_if_missing(
        "counterparty_phones",
        sa.Column("phone_operations", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("counterparty_phones", "phone_operations")
    op.drop_column("tenants", "invoice_due_day_operations")
