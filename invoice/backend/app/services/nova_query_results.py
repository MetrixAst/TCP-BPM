"""Нормализация результатов op=query из Nova/COM (columns+items → dict rows)."""

from __future__ import annotations

from typing import Any


def query_step_to_dicts(step: Any) -> list[dict[str, Any]]:
    if not isinstance(step, dict):
        return []
    items = step.get("items")
    if not isinstance(items, list) or not items:
        return []

    columns = step.get("columns")
    if items and isinstance(items[0], dict):
        return [row for row in items if isinstance(row, dict)]

    col_names = [str(col) for col in columns] if isinstance(columns, list) else []
    rows: list[dict[str, Any]] = []

    if items and isinstance(items[0], (list, tuple)):
        for item in items:
            if not isinstance(item, (list, tuple)):
                continue
            row = {
                col_names[i]: item[i]
                for i in range(min(len(col_names), len(item)))
            }
            rows.append(row)
        return rows

    if col_names and not isinstance(items[0], (list, dict)):
        rows.append(
            {col_names[i]: items[i] for i in range(min(len(col_names), len(items)))}
        )
        return rows

    return []


def query_step_first_row(step: Any) -> dict[str, Any]:
    rows = query_step_to_dicts(step)
    return rows[0] if rows else {}
