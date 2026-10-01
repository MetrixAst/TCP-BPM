"""tenants.xlsx_parser_key

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic_ddl_utils import add_column_if_missing

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "tenants",
        sa.Column("xlsx_parser_key", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    from alembic import op

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("xlsx_parser_key")
