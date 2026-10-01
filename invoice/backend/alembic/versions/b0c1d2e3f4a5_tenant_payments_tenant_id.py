"""tenant_payments.tenant_id — real FK, backfilled from ip_name/legal_name

Before this, every tenant-scoping query on tenant_payments matched by
`ip_name == tenant.legal_name` — a free-text column with no uniqueness
constraint at the DB level. Two tenants sharing/near-matching a legal_name
(same or different TRC) could see, and 1C sync could silently overwrite,
each other's invoices/payments. See audit from 2026-08-25.

This migration adds a nullable `tenant_id` FK and backfills it using the
*same* legal_name match the app used to rely on at query time — but only for
`ip_name` values that map to exactly one tenant. Ambiguous matches (an
ip_name shared by >1 tenant) and orphaned ones (no matching tenant) are left
NULL rather than guessed, and reported so they can be fixed by hand — the
whole point of this migration is to stop trusting an ambiguous match, so the
backfill must not re-introduce the same ambiguity it's removing.

Application code (see payment_service.py) now filters by tenant_id instead
of ip_name==legal_name; a row left NULL by this migration simply won't show
up in a tenant-scoped query until manually assigned — safer than guessing
wrong.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing, column_exists

revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_tenant_payments_tenant_id"


def upgrade() -> None:
    add_column_if_missing(
        "tenant_payments",
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
    )

    bind = op.get_bind()
    existing_indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("tenant_payments")}
    if _INDEX_NAME not in existing_indexes:
        op.create_index(_INDEX_NAME, "tenant_payments", ["tenant_id"])

    # Only unambiguous legal_name -> single tenant_id mappings are backfilled.
    unambiguous = bind.exec_driver_sql(
        """
        SELECT legal_name, min(id) AS tenant_id
        FROM tenants
        GROUP BY legal_name
        HAVING count(*) = 1
        """
    ).fetchall()

    updated_total = 0
    for legal_name, tenant_id in unambiguous:
        result = bind.execute(
            sa.text(
                """
                UPDATE tenant_payments
                SET tenant_id = :tenant_id
                WHERE ip_name = :legal_name AND tenant_id IS NULL
                """
            ),
            {"tenant_id": tenant_id, "legal_name": legal_name},
        )
        updated_total += result.rowcount or 0

    remaining = bind.exec_driver_sql(
        "SELECT ip_name, count(*) FROM tenant_payments WHERE tenant_id IS NULL GROUP BY ip_name"
    ).fetchall()
    if remaining:
        details = "; ".join(f"{ip_name!r} x{count}" for ip_name, count in remaining)
        print(
            f"[b0c1d2e3f4a5] backfilled {updated_total} tenant_payments rows; "
            f"{sum(c for _, c in remaining)} rows across {len(remaining)} distinct "
            f"ip_name value(s) could NOT be matched to exactly one tenant and were "
            f"left with tenant_id=NULL (ambiguous legal_name or no matching tenant): "
            f"{details}. These rows are invisible to tenant-scoped queries until "
            f"resolved by hand — check for tenants sharing a legal_name, or "
            f"historical ip_name values that no longer match any tenant."
        )
    else:
        print(f"[b0c1d2e3f4a5] backfilled all {updated_total} tenant_payments rows.")


def downgrade() -> None:
    if column_exists("tenant_payments", "tenant_id"):
        op.drop_index(_INDEX_NAME, table_name="tenant_payments")
        op.drop_column("tenant_payments", "tenant_id")
