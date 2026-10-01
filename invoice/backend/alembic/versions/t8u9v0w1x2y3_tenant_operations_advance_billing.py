"""tenant operations/marketing advance billing flag

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-09-02

Запрошено 2026-09-02 для Maxi Mall/Astranium: эксплуатация и маркетинг у них
выставляются авансом за СЛЕДУЮЩИЙ месяц, как аренда (тот же +1 сдвиг в
invoice_report.py::_item_name_with_payment_month) — в отличие от всех
остальных ТРЦ, где эта категория по-прежнему "по факту" за текущий месяц.
server_default=false — поведение не меняется ни для одного существующего
тенанта, кроме тех, кому явно включат флаг через админку.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "t8u9v0w1x2y3"
down_revision: Union[str, None] = "s7t8u9v0w1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "tenants",
        sa.Column(
            "invoice_operations_advance_billing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "invoice_operations_advance_billing")
