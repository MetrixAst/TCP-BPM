"""tenant SMTP settings for email mailings

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-07-21

Идемпотентно (ADD/DROP IF EXISTS). Откат: alembic downgrade r8s9t0u1v2w3
Перед reverse-деплоем образа без этой миграции — сначала downgrade, иначе
Can't locate revision identified by 's9t0u1v2w3x4'.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_host VARCHAR(255)")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_port INTEGER")
    op.execute(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_use_starttls "
        "BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_username VARCHAR(255)")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_password VARCHAR(255)")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS smtp_from_email VARCHAR(255)")


def downgrade() -> None:
    """Откат ревизии — безопасный DROP IF EXISTS (для reverse через alembic)."""
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS smtp_from_email")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS smtp_password")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS smtp_username")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS smtp_use_starttls")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS smtp_port")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS smtp_host")
