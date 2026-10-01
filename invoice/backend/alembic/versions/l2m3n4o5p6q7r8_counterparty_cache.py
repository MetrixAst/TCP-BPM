"""counterparty_cache — снимок контрагентов из 1С в PostgreSQL

Revision ID: l2m3n4o5p6q7r8
Revises: k1l2m3n4o5p6q7
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "l2m3n4o5p6q7r8"
down_revision: Union[str, None] = "k1l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS counterparty_cache (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            data JSONB,
            total_from_1c INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'idle',
            error TEXT,
            started_at TIMESTAMPTZ,
            synced_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_counterparty_cache_status
        ON counterparty_cache (status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_counterparty_cache_status")
    op.execute("DROP TABLE IF EXISTS counterparty_cache")
