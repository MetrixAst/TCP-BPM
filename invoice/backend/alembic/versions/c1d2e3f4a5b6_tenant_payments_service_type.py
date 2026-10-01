"""tenant_payments.service_type

Redesign of the "Реестр" page: rows switch from one-per-counterparty to
one-per-invoice, and the requested columns include "тип счёта" (rent/
utilities/marketing/signage/assp). That needs to be a stored column, not
resolved on the fly per request — resolving it live means fetching each
invoice's 1C line items per page view, which for OData-backed tenants is a
real network round-trip per invoice (see app/services/invoice_service_type.py
docstring and the 2026-08-25 redesign discussion).

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_tenant_payments_service_type"


def upgrade() -> None:
    add_column_if_missing(
        "tenant_payments",
        sa.Column("service_type", sa.String(length=64), nullable=True),
    )
    bind = op.get_bind()
    existing_indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("tenant_payments")}
    if _INDEX_NAME not in existing_indexes:
        op.create_index(_INDEX_NAME, "tenant_payments", ["service_type"])


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="tenant_payments")
    op.drop_column("tenant_payments", "service_type")
