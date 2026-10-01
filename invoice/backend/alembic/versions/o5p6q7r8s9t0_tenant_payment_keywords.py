"""tenant payment type keywords (per tenant)

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-06-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        "payment_keywords_rent",
        "payment_keywords_utilities",
        "payment_keywords_operations",
    ):
        add_column_if_missing(
            "tenants",
            sa.Column(col, sa.Text(), nullable=True),
        )


def downgrade() -> None:
    for col in (
        "payment_keywords_operations",
        "payment_keywords_utilities",
        "payment_keywords_rent",
    ):
        op.drop_column("tenants", col)
