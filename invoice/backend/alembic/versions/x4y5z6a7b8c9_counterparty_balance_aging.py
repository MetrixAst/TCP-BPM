"""aging (долг по срокам) в counterparty_balances

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-08-07

BUH: onec.buh.balance → aging. Та же секция того же ответа, что и
by_counterparty — 1С уже считает и отдаёт, раньше выбрасывалось при парсинге.
Бакеты по BUH-API-reference: current/days30/days60/days90/over120/unknown/total.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "aging_current",
    "aging_30",
    "aging_60",
    "aging_90",
    "aging_over120",
    "aging_unknown",
    "aging_total",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(
            f"ALTER TABLE counterparty_balances ADD COLUMN IF NOT EXISTS {column} NUMERIC(18, 2)"
        )


def downgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE counterparty_balances DROP COLUMN IF EXISTS {column}")
