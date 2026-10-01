"""unique constraint on tenants.nova_organization_id

nova_organization_id had no uniqueness guarantee at all: NovaBuh1CClient
resolves which tenant a PDF belongs to purely by this column
(_resolve_tenant_for_pdf), so a fat-fingered duplicate on tenant create/update
means .first() silently picks one of two active tenants — stamping one
tenant's invoice PDF with another tenant's signature/bank requisites (see
audit from 2026-08-25).

A plain UNIQUE constraint is safe here even though the column is nullable:
Postgres does not treat NULL = NULL for uniqueness, so tenants without a Nova
org (NULL) are unaffected — only two *active, non-null* duplicates would ever
conflict, and that's exactly the misconfiguration this closes.

Revision ID: a9b0c1d2e3f4
Revises: z7a8b9c0d1e2
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op

from alembic_ddl_utils import constraint_exists

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "z7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT_NAME = "uq_tenants_nova_organization_id"


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.exec_driver_sql(
        """
        SELECT nova_organization_id, array_agg(id) AS tenant_ids
        FROM tenants
        WHERE nova_organization_id IS NOT NULL
        GROUP BY nova_organization_id
        HAVING count(*) > 1
        """
    ).fetchall()
    if duplicates:
        details = "; ".join(
            f"nova_organization_id={row[0]} shared by tenants {list(row[1])}" for row in duplicates
        )
        raise RuntimeError(
            "Cannot add uq_tenants_nova_organization_id: existing duplicate "
            f"nova_organization_id values found ({details}). Fix the "
            "conflicting tenants (each Nova org must map to exactly one "
            "tenant) before re-running this migration."
        )

    if not constraint_exists("tenants", _CONSTRAINT_NAME):
        op.create_unique_constraint(_CONSTRAINT_NAME, "tenants", ["nova_organization_id"])


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "tenants", type_="unique")
