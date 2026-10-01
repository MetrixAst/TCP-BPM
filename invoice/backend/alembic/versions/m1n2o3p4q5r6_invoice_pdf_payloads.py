"""invoice_pdf_payloads — cached 1C-native invoice data for PDF generation

Revision ID: m1n2o3p4q5r6
Revises: f4a5b6c7d8e9
Create Date: 2026-08-31

См. app/services/invoice_pdf_cache.py и app/models/invoice_pdf_payload.py
docstrings — кэш структурированных данных счёта (не PDF-байтов), чтобы
повторный/любой просмотр уже виденного счёта не бил в живую 1С. JSON, не
JSONB — намеренно портируемый тип, см. модель.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from alembic_ddl_utils import table_exists

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("invoice_pdf_payloads"):
        return
    op.create_table(
        "invoice_pdf_payloads",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.String(length=64), nullable=False),
        # nullable — a row can exist purely to throttle force-refresh
        # attempts before any payload ever passed the validity gate, see
        # the model docstring.
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_force_refresh_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "invoice_id"),
    )


def downgrade() -> None:
    if table_exists("invoice_pdf_payloads"):
        op.drop_table("invoice_pdf_payloads")
