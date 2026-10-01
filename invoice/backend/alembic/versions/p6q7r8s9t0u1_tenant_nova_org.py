"""tenant nova organization id and connection mode

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-06-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "tenants",
        sa.Column("nova_organization_id", sa.Integer(), nullable=True),
    )
    add_column_if_missing(
        "tenants",
        sa.Column("one_c_connection_mode", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "one_c_connection_mode")
    op.drop_column("tenants", "nova_organization_id")
