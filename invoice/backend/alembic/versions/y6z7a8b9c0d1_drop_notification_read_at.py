"""drop notifications.read_at (мёртвое поле — вебхук-подтверждение прочтения не обрабатывается)

Revision ID: y6z7a8b9c0d1
Revises: x4y5z6a7b8c9
Create Date: 2026-08-07

read_at/NotificationStatus.READ никогда не проставлялись ничем, кроме
собственных /read эндпоинта и mark_as_read (оба удалены) — Green API webhook
на прочтение у нас не обрабатывается (whatsapp_jobs.process_webhook_job —
заглушка). delivered_at оставляем — оно реально проставляется автоматически
при успешной отправке (whatsapp_jobs.deliver_notification/deliver_raw_message).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "y6z7a8b9c0d1"
down_revision: Union[str, None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS read_at")


def downgrade() -> None:
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMP WITH TIME ZONE")
