"""снимок взаиморасчётов balance (debit/credit) по контрагентам

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-07-26

BUH: onec.buh.balance → by_counterparty.
Не трогает tenant_payments / реестр счетов.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS counterparty_balances (
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            counterparty_id VARCHAR(64) NOT NULL,
            counterparty_name VARCHAR(512),
            debit NUMERIC(18, 2) NOT NULL DEFAULT 0,
            credit NUMERIC(18, 2) NOT NULL DEFAULT 0,
            synced_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, counterparty_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_counterparty_balances_tenant_synced
        ON counterparty_balances (tenant_id, synced_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_counterparty_balances_tenant_synced")
    op.execute("DROP TABLE IF EXISTS counterparty_balances")
