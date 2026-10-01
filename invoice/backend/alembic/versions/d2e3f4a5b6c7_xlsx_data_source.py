"""xlsx as an alternate data source: tenants.xlsx_priority, tenant_payments.source, tenant_data_files

New feature (2026-08-26): some TCs keep a manually-updated Excel alongside
1C (or instead of it) that's more current than 1C — see
app/services/xlsx_import/. This is the schema slice, built as a reference
implementation against Maxi Mall's real file
("Оплата_Аренды ТРЦ УК август.xlsx").

- tenants.xlsx_priority: disabled (default) / fallback_on_1c_failure /
  prefer_xlsx — per-tenant, same shape as one_c_connection_mode.
- tenant_payments.source: "one_c" (backfilled for every existing row) /
  "xlsx" — provenance didn't exist anywhere before this; see the audit note
  in app/models/payment.py for why that was a real gap (TRC-scope-leak
  investigation, 2026-08-26).
- tenant_data_files: one row per uploaded .xlsx (versioned, audit trail —
  see app/models/tenant_data_file.py).

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import add_column_if_missing, table_exists

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "tenants",
        sa.Column("xlsx_priority", sa.String(length=32), nullable=False, server_default="disabled"),
    )
    add_column_if_missing(
        "tenant_payments",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="one_c"),
    )

    if not table_exists("tenant_data_files"):
        op.create_table(
            "tenant_data_files",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("original_filename", sa.String(length=512), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=True),
            sa.Column("file_bytes", sa.LargeBinary(), nullable=True),
            sa.Column("uploaded_by", sa.String(length=128), nullable=True),
            sa.Column(
                "uploaded_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("parse_summary", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index(
            "ix_tenant_data_files_tenant_id", "tenant_data_files", ["tenant_id"]
        )
        op.create_index(
            "ix_tenant_data_files_status", "tenant_data_files", ["status"]
        )
        op.create_index(
            "ix_tenant_data_files_is_active", "tenant_data_files", ["is_active"]
        )


def downgrade() -> None:
    if table_exists("tenant_data_files"):
        op.drop_table("tenant_data_files")
    with op.batch_alter_table("tenant_payments") as batch_op:
        batch_op.drop_column("source")
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("xlsx_priority")
