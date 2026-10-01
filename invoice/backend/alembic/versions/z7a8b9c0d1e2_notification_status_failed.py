"""значение FAILED в notificationstatus

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-08-24

До этого статус уведомления был либо SENT (создано, попытка отправки могла
провалиться), либо DELIVERED — в БД невозможно было отличить "Green API
отправку не принял" от "просто пока не подтверждено". Теперь
whatsapp_jobs.deliver_notification проставляет FAILED при неуспехе (после
ретраев на транспортном уровне в whatsapp_service._session).

ALTER TYPE ... ADD VALUE не может выполняться в открытой транзакции на части
версий PostgreSQL — коммитим текущую транзакцию перед этой командой (см.
https://www.postgresql.org/docs/current/sql-altertype.html), как и в
v2w3x4y5z6a7_payment_partial_status.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z7a8b9c0d1e2"
down_revision: Union[str, None] = "y6z7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # sa.Enum(NotificationStatus) без values_callable хранит имена членов
    # Python Enum (SENT/DELIVERED), не .value ("sent"/"delivered") — тот же
    # паттерн, что в v2w3x4y5z6a7_payment_partial_status.py (PAID/UNPAID/OVERDUE).
    existing = {v for v in bind.execute(
        sa.text("SELECT unnest(enum_range(NULL::notificationstatus))::text")
    ).scalars().all()}
    if "FAILED" not in existing:
        op.execute("COMMIT")
        op.execute("ALTER TYPE notificationstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения enum-типа — оставляем
    # 'failed' в типе, откатывать нечего (см. v2w3x4y5z6a7 для того же паттерна).
    pass
