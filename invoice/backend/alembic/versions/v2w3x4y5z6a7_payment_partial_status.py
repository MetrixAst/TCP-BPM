"""частичная оплата: paid_amount на tenant_payments + значение PARTIAL в paymentstatus

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-08-03

Счёт теперь считается "paid" только когда покрыт полностью (с небольшим
допуском на округление 1С, см. payment_status_rules.PAID_TOLERANCE) — раньше
порог был 80% суммы. Между 0% и порогом полной оплаты статус — PARTIAL.

ALTER TYPE ... ADD VALUE не может выполняться в открытой транзакции на части
версий PostgreSQL — коммитим текущую транзакцию перед этой командой (см.
https://www.postgresql.org/docs/current/sql-altertype.html), возвращаемся к
обычному поведению Alembic для остальных операций миграции.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
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

    if not _has_column(inspector, "tenant_payments", "paid_amount"):
        op.add_column("tenant_payments", sa.Column("paid_amount", sa.Integer(), nullable=True))

    # Enum-значения в БД — имена членов Python Enum (PAID/UNPAID/OVERDUE), не их
    # value ("paid"/"unpaid"/"overdue") — так уже сериализует SQLAlchemy Enum()
    # без явного values_callable, менять это задним числом не будем.
    existing = {v.upper() for v in bind.execute(
        sa.text(
            "SELECT unnest(enum_range(NULL::paymentstatus))::text"
        )
    ).scalars().all()}
    if "PARTIAL" not in existing:
        op.execute("COMMIT")
        op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'PARTIAL'")


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения enum-типа (ALTER TYPE ... DROP
    # VALUE не существует) — оставляем PARTIAL в типе как есть, откатываем только
    # колонку. Понижение версии на БД, где уже есть строки со status=PARTIAL,
    # потребует ручной миграции данных перед downgrade — намеренно не скрываем
    # эту сложность автоматическим DROP TYPE/CREATE TYPE.
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_column(inspector, "tenant_payments", "paid_amount"):
        op.drop_column("tenant_payments", "paid_amount")
