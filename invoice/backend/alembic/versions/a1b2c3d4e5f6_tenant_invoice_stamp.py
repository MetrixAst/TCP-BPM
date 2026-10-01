"""tenant invoice stamp and requisites

Revision ID: a1b2c3d4e5f6
Revises: 13c92445c5c8
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "13c92445c5c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        sa.Column("stamp_file_path", sa.String(length=512), nullable=True),
        sa.Column("invoice_iik", sa.String(length=34), nullable=True),
        sa.Column("invoice_kbe", sa.String(length=8), nullable=True),
        sa.Column("invoice_bank_name", sa.String(length=255), nullable=True),
        sa.Column("invoice_bank_bik", sa.String(length=16), nullable=True),
        sa.Column("invoice_payment_knp", sa.String(length=16), nullable=True),
        sa.Column("invoice_supplier_address", sa.Text(), nullable=True),
        sa.Column("invoice_executor_name", sa.String(length=128), nullable=True),
        sa.Column("invoice_contract_text", sa.String(length=255), nullable=True),
    ):
        add_column_if_missing("tenants", col)


def downgrade() -> None:
    op.drop_column("tenants", "invoice_contract_text")
    op.drop_column("tenants", "invoice_executor_name")
    op.drop_column("tenants", "invoice_supplier_address")
    op.drop_column("tenants", "invoice_payment_knp")
    op.drop_column("tenants", "invoice_bank_bik")
    op.drop_column("tenants", "invoice_bank_name")
    op.drop_column("tenants", "invoice_kbe")
    op.drop_column("tenants", "invoice_iik")
    op.drop_column("tenants", "stamp_file_path")
