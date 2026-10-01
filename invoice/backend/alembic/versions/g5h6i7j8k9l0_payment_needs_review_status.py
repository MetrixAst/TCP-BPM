"""paymentstatus: значение NEEDS_REVIEW для xlsx-строк с битым источником

Revision ID: g5h6i7j8k9l0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-28

xlsx-импорт (см. app/services/xlsx_import/parsers/avantage.py) может
встретить формулу-ошибку (#REF! и т.п.) в столбцах "оплачено"/"остаток" —
0 там значит "неизвестно", а не "оплачено полностью"/"ничего не оплачено".
Без отдельного статуса такие строки садились на PAID (см.
xlsx_import/normalize.py._status до этого коммита) — молча неверно для
любого, кто смотрит на реестр/дашборд. 1С-путь это значение никогда не
производит.

Тот же приём, что и у v2w3x4y5z6a7 (PARTIAL) — ALTER TYPE ... ADD VALUE не
может идти внутри открытой транзакции на части версий PostgreSQL, коммитим
перед ней.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g5h6i7j8k9l0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Enum-значения в БД — имена членов Python Enum (PAID/PARTIAL/...), не их
    # .value ("paid"/"partial"/...) — см. тот же комментарий в v2w3x4y5z6a7.
    existing = {v.upper() for v in bind.execute(
        sa.text("SELECT unnest(enum_range(NULL::paymentstatus))::text")
    ).scalars().all()}
    if "NEEDS_REVIEW" not in existing:
        op.execute("COMMIT")
        op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'NEEDS_REVIEW'")


def downgrade() -> None:
    # PostgreSQL не поддерживает ALTER TYPE ... DROP VALUE — как и в
    # v2w3x4y5z6a7, оставляем значение в типе; откат на БД, где уже есть
    # строки со status=NEEDS_REVIEW, требует ручной миграции данных до
    # downgrade.
    pass
