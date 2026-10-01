"""clear manual tenant invoice requisites (now from 1C only)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-29

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Ручные реквизиты из старой админки; в PDF берутся из 1С.
_COLUMNS = (
    "invoice_iik",
    "invoice_kbe",
    "invoice_bank_name",
    "invoice_bank_bik",
    "invoice_payment_knp",
    "invoice_supplier_address",
    "invoice_contract_text",
)


def upgrade() -> None:
    sets = ", ".join(f"{col} = NULL" for col in _COLUMNS)
    op.execute(f"UPDATE tenants SET {sets}")


def downgrade() -> None:
    pass
