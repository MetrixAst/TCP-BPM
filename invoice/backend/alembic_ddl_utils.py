"""Идемпотентные DDL-хелперы для миграций (create_all уже создаёт колонки из моделей)."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


def _inspector():
    return inspect(op.get_bind())


def table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return any(c["name"] == column_name for c in _inspector().get_columns(table_name))


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def constraint_exists(table_name: str, constraint_name: str) -> bool:
    if not table_exists(table_name):
        return False
    inspector = _inspector()
    names = {c["name"] for c in inspector.get_unique_constraints(table_name)}
    names |= {i["name"] for i in inspector.get_indexes(table_name)}
    return constraint_name in names
