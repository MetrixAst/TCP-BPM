"""notifications.green_api_id_message — сопоставление с webhook-статусом Green API

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8
Create Date: 2026-09-10

Реальный инцидент 2026-09-09 (Maxi Mall, "Astranium"): 111 счетов должникам
ушли одной пачкой за минуту, инстанс словил временную блокировку от WhatsApp,
104 из 111 застряли на статусе "sent" — но наша БД раньше проставляла
Notification.status=DELIVERED сразу по факту успешного HTTP-ответа Green API
(см. whatsapp_jobs.deliver_notification), не дожидаясь реального подтверждения
доставки. Этот столбец хранит idMessage, который Green API возвращает на
отправку, чтобы потом сопоставить с ним пришедший позже outgoingMessageStatus
вебхук (delivered/read/failed/noAccount/suspended) и обновить статус на
основе того, что реально произошло, а не оптимистично.

nullable — существующие строки (все, отправленные до этого фикса) не имеют
idMessage и не могут быть ретроактивно сверены; для них резерв — фактическая
проверка через Green API GetChatHistory (сделано вручную для инцидента
2026-09-09, при необходимости повторить также вручную для более старых строк).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "w4x5y6z7a8b9"
down_revision: Union[str, None] = "v3w4x5y6z7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    try:
        return any(col["name"] == column_name for col in inspector.get_columns(table_name))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _has_column(inspector, "notifications", "green_api_id_message"):
        op.add_column(
            "notifications",
            sa.Column("green_api_id_message", sa.String(), nullable=True),
        )
        op.create_index(
            "ix_notifications_green_api_id_message",
            "notifications",
            ["green_api_id_message"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_column(inspector, "notifications", "green_api_id_message"):
        op.drop_index("ix_notifications_green_api_id_message", table_name="notifications")
        op.drop_column("notifications", "green_api_id_message")
