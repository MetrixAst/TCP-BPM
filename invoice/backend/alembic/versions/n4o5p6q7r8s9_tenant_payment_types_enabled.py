"""tenant payment type enable flags

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-06-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        "payment_rent_enabled",
        "payment_utilities_enabled",
        "payment_operations_enabled",
    ):
        add_column_if_missing(
            "tenants",
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    for col in (
        "payment_operations_enabled",
        "payment_utilities_enabled",
        "payment_rent_enabled",
    ):
        op.drop_column("tenants", col)
