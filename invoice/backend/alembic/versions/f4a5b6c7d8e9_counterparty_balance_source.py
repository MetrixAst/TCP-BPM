"""counterparty_balances.source — protect xlsx-derived balance rows from 1C sync overwrite

Companion to tenant_payments.source (see d2e3f4a5b6c7). 1C balance sync
(replace_balances_for_tenant) does a full delete+reinsert per tenant on
every run — without this column that would silently wipe any
xlsx-computed balance row on the next hourly sync. The guard added in
counterparty_balance_service.py checks this column directly rather than
re-deriving it from Tenant.xlsx_priority, so a balance row stays
xlsx-sourced ("sticky") until the next xlsx re-import touches it, whatever
the tenant's current xlsx_priority setting is.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic_ddl_utils import add_column_if_missing

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "counterparty_balances",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="one_c"),
    )


def downgrade() -> None:
    from alembic import op

    with op.batch_alter_table("counterparty_balances") as batch_op:
        batch_op.drop_column("source")
