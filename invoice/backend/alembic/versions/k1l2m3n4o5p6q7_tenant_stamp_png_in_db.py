"""PNG печати и подписи в PostgreSQL (переживают деплой без PVC).

Revision ID: k1l2m3n4o5p6q7
Revises: j0k1l2m3n4o5p6
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "k1l2m3n4o5p6q7"
down_revision: Union[str, None] = "j0k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stamp_png BYTEA")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS signature_png BYTEA")


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS signature_png")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS stamp_png")
