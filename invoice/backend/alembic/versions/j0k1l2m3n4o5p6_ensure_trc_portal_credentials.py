"""ensure trc portal credentials columns (safe prod redeploy)

Revision ID: j0k1l2m3n4o5p6
Revises: i9j0k1l2m3n4
Create Date: 2026-06-07

Идемпотентно добавляет portal_username / portal_password_hash в trcs.
Без alembic_ddl_utils — только PostgreSQL IF NOT EXISTS (как f6a7b8 / g7h8).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "j0k1l2m3n4o5p6"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE trcs ADD COLUMN IF NOT EXISTS portal_username VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE trcs ADD COLUMN IF NOT EXISTS portal_password_hash VARCHAR(255)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_trcs_portal_username
        ON trcs (portal_username)
        """
    )


def downgrade() -> None:
    pass
