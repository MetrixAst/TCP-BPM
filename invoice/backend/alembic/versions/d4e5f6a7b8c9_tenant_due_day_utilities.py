"""tenant due day utilities

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "tenants",
        sa.Column("invoice_due_day_utilities", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "invoice_due_day_utilities")
