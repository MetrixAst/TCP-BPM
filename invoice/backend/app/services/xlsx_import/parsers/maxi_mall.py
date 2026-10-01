"""Парсер под реальный файл Maxi Mall
("Оплата_Аренды ТРЦ УК август.xlsx", разобран 2026-08-26) — эталонная
реализация per-tenant парсера, см. app/services/xlsx_import/registry.py.

Формат (подтверждено на реальном файле):
- Листы "Начисление <МЕСЯЦ>" (кириллица, ИЮНЬ/ИЮЛЬ/АВГУСТ...) — один на
  период, строка = арендатор × 4 типа начисления (Аренда/КУ/Долг
  пред.периода/Прочее), с разбивкой начислено/оплачено/остаток. Это
  единственный лист, из которого реально импортируем.
- "Журнал поступлений" — построчный журнал платежей, из которого
  агрегируется "оплачено" в листах "Начисление". Не импортируем в v1 —
  "Начисление" уже даёт то, что нужно для статуса оплаты/напоминаний
  (paid/unpaid по остатку), без построчных дат отдельных платежей.
- "Общий свод оплат" — чистый пивот-агрегат по всем месяцам, данных для
  импорта не даёт. Используется здесь как ВСТРОЕННАЯ САМОПРОВЕРКА: сумма
  того, что мы сами насчитали по листам "Начисление", должна совпасть с
  тем, что в этом листе — расхождение значит формат файла поехал (напр.
  ТЦ переставил колонки), а не что наш парсер молча съел данные неверно.

Важная находка: формат "плывёт" даже внутри одного файла — в листе
"Начисление ИЮНЬ" нет колонки "Статус" вообще (сдвигает "Примечание" на
одну колонку левее), в ИЮЛЬ/АВГУСТ она есть. Поэтому колонки резолвятся по
СОДЕРЖИМОМУ заголовка (строка 3), а не по фиксированному индексу.
"""
from __future__ import annotations

import re
from typing import Optional

from openpyxl import load_workbook

from app.services.xlsx_import.types import ParseResult, RawChargeRow

PARSER_KEY = "maxi_mall"

_CHARGE_SHEET_PREFIX = "Начисление"
_SUMMARY_SHEET = "Общий свод оплат"

_HEADER_ROW = 3
_DATA_START_ROW = 4

_MONTHS_RU = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}

# Порог "это ноль" при решении, создавать ли строку для (арендатор, тип
# начисления) — большинство строк ненулевые ровно по 1-2 из 4 типов,
# остальное честные нули (см. пример: Прочее=None/0/0 у большинства
# арендаторов). Не тот же допуск, что PAID_TOLERANCE — там речь о покрытии
# суммы, здесь — о "было ли вообще начисление этого типа".
_ZERO_EPS = 0.01

# Допуск сверки с "Общий свод оплат" — сумма по ~150 строк с плавающей
# точкой в 1С/Excel, несколько тенге расхождения на округлениях ожидаемы;
# на порядок больше пропустил бы что-то реально пропавшее.
_TOTALS_CHECK_TOLERANCE = 50.0


def _normalize_header(raw: object) -> str:
    return " ".join(str(raw or "").replace("\n", " ").lower().split())


def _classify_headers(ws, header_row: int) -> dict:
    """Колонка по смыслу заголовка, а не по индексу — см. докстринг модуля
    про "Долг\\nост. ₸" (без "пр.пер.") в отличие от "Долг пр.пер.\\nначисл. ₸"
    и про отсутствие "Статус" в листе ИЮНЬ."""
    name_col = unit_col = brand_col = zone_col = None
    charges: dict[tuple[str, str], int] = {}

    for col in range(1, ws.max_column + 1):
        header = _normalize_header(ws.cell(row=header_row, column=col).value)
        if not header:
            continue

        if header == "арендатор":
            name_col = col
            continue
        if header.startswith("помещ"):
            unit_col = col
            continue
        if header == "бренд":
            brand_col = col
            continue
        if header == "зона":
            zone_col = col
            continue
        if "итого" in header or "сбора" in header or header in ("статус", "примечание", "№"):
            continue

        if "начисл" in header:
            phase = "charged"
        elif "оплач" in header:
            phase = "paid"
        elif re.search(r"\bост\b", header) or header.endswith("ост. ₸") or " ост " in f" {header} ":
            phase = "remainder"
        else:
            continue

        if "аренд" in header:
            metric = "rent"
        elif re.search(r"\bку\b", header):
            metric = "utilities"
        elif "долг" in header:
            metric = "debt"
        elif "прочее" in header or "% с обор" in header:
            metric = "other"
        else:
            continue

        charges[(metric, phase)] = col

    if name_col is None:
        raise ValueError(f"Колонка «Арендатор» не найдена (строка {header_row})")

    return {
        "name_col": name_col,
        "unit_col": unit_col,
        "brand_col": brand_col,
        "zone_col": zone_col,
        "charges": charges,
    }


def _extract_period(sheet_name: str, title_cell: object) -> Optional[str]:
    month_match = None
    for name, num in _MONTHS_RU.items():
        if name.upper() in sheet_name.upper():
            month_match = num
            break
    if month_match is None:
        return None

    year_match = re.search(r"\b(20\d{2})\b", str(title_cell or ""))
    if not year_match:
        return None
    return f"{year_match.group(1)}-{month_match:02d}"


def _cell_float(ws, row: int, col: Optional[int]) -> float:
    if col is None:
        return 0.0
    val = ws.cell(row=row, column=col).value
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _is_zero(*values: float) -> bool:
    return all(abs(v) < _ZERO_EPS for v in values)


def _parse_charge_sheet(ws, sheet_name: str, period: str, warnings: list[str]) -> list[RawChargeRow]:
    header_map = _classify_headers(ws, _HEADER_ROW)
    rows: list[RawChargeRow] = []

    for row_num in range(_DATA_START_ROW, ws.max_row + 1):
        raw_name = ws.cell(row=row_num, column=header_map["name_col"]).value
        # Пустой "Арендатор" — либо реально пустая хвостовая строка, либо
        # строка "ИТОГО ПО ТРЦ" (мёрдж-ячейка A:E — только у левой ячейки
        # мёрджа есть значение, у остальных, включая C, всегда None). Оба
        # случая корректно пропускаются одной проверкой.
        if raw_name is None or not str(raw_name).strip():
            continue
        name = str(raw_name).strip()

        brand = ws.cell(row=row_num, column=header_map["brand_col"]).value if header_map["brand_col"] else None
        unit = ws.cell(row=row_num, column=header_map["unit_col"]).value if header_map["unit_col"] else None
        zone = ws.cell(row=row_num, column=header_map["zone_col"]).value if header_map["zone_col"] else None

        for metric in ("rent", "utilities", "debt", "other"):
            charged = _cell_float(ws, row_num, header_map["charges"].get((metric, "charged")))
            paid = _cell_float(ws, row_num, header_map["charges"].get((metric, "paid")))
            remainder = _cell_float(ws, row_num, header_map["charges"].get((metric, "remainder")))
            if _is_zero(charged, paid, remainder):
                continue
            rows.append(
                RawChargeRow(
                    raw_name=name,
                    period=period,
                    charge_type=metric,
                    charged=charged,
                    paid=paid,
                    remainder=remainder,
                    brand=str(brand).strip() if brand else None,
                    unit=str(unit).strip() if unit else None,
                    zone=str(zone).strip() if zone else None,
                    sheet_name=sheet_name,
                    row_number=row_num,
                )
            )

    if not rows:
        warnings.append(f'Лист "{sheet_name}": ни одной строки с данными не найдено')
    return rows


_METRIC_LABEL_IN_SUMMARY = {
    "rent": "аренда",
    "utilities": "ку",
    "debt": "долг пр.пер.",
    "other": "% с обор./проч.",
}
_MONTH_LABEL_RU = {v: k.upper() for k, v in _MONTHS_RU.items()}


def _summary_totals(wb) -> dict[tuple[str, str], float]:
    """(period, metric) -> начислено ₸, из листа "Общий свод оплат"."""
    if _SUMMARY_SHEET not in wb.sheetnames:
        return {}
    ws = wb[_SUMMARY_SHEET]
    out: dict[tuple[str, str], float] = {}
    header_row = None
    for r in range(1, min(ws.max_row, 10) + 1):
        if _normalize_header(ws.cell(row=r, column=1).value) == "№":
            header_row = r
            break
    if header_row is None:
        return {}

    col_map = {_normalize_header(ws.cell(row=header_row, column=c).value): c for c in range(1, ws.max_column + 1)}
    month_col = col_map.get("мес.")
    type_col = col_map.get("вид платежа")
    charged_col = col_map.get("начислено ₸")
    if not (month_col and type_col and charged_col):
        return {}

    metric_by_label = {v: k for k, v in _METRIC_LABEL_IN_SUMMARY.items()}
    for r in range(header_row + 1, ws.max_row + 1):
        month_label = str(ws.cell(row=r, column=month_col).value or "").strip().upper()
        type_label = _normalize_header(ws.cell(row=r, column=type_col).value)
        metric = metric_by_label.get(type_label)
        if not metric or not month_label:
            continue
        month_num = _MONTHS_RU.get(month_label.lower())
        if not month_num:
            continue
        charged = ws.cell(row=r, column=charged_col).value
        try:
            charged = float(charged)
        except (TypeError, ValueError):
            continue
        # Год неизвестен на этом листе — сверяем по (месяц, метрика) поверх
        # всех периодов файла с этим месяцем (в пределах одного файла период
        # с одинаковым месяцем встречается максимум раз).
        out[(month_num, metric)] = charged
    return out


def _totals_check(wb, rows: list[RawChargeRow]) -> dict[str, dict]:
    computed: dict[tuple[int, str], float] = {}
    for row in rows:
        month_num = int(row.period[5:7])
        computed[(month_num, row.charge_type)] = computed.get((month_num, row.charge_type), 0.0) + row.charged

    summary = _summary_totals(wb)
    result: dict[str, dict] = {}
    for (month_num, metric), expected in summary.items():
        actual = computed.get((month_num, metric), 0.0)
        diff = abs(actual - expected)
        key = f"{_MONTH_LABEL_RU.get(month_num, month_num)}:{metric}"
        result[key] = {
            "expected": expected,
            "actual": actual,
            "diff": diff,
            "ok": diff <= _TOTALS_CHECK_TOLERANCE,
        }
    return result


def parse(file_bytes: bytes) -> ParseResult:
    wb = load_workbook(filename=__import__("io").BytesIO(file_bytes), data_only=True)

    all_rows: list[RawChargeRow] = []
    periods: list[str] = []
    warnings: list[str] = []

    for sheet_name in wb.sheetnames:
        if not sheet_name.strip().startswith(_CHARGE_SHEET_PREFIX):
            continue
        ws = wb[sheet_name]
        title_cell = ws.cell(row=1, column=1).value
        period = _extract_period(sheet_name, title_cell)
        if not period:
            warnings.append(f'Лист "{sheet_name}": не удалось определить период (месяц/год) из названия/заголовка')
            continue
        periods.append(period)
        all_rows.extend(_parse_charge_sheet(ws, sheet_name, period, warnings))

    totals_check = _totals_check(wb, all_rows)
    for key, check in totals_check.items():
        if not check["ok"]:
            warnings.append(
                f'Сверка с "{_SUMMARY_SHEET}" не сошлась для {key}: '
                f'наш подсчёт={check["actual"]:.2f}, в файле={check["expected"]:.2f} '
                f'(разница {check["diff"]:.2f} ₸)'
            )

    return ParseResult(rows=all_rows, periods=periods, totals_check=totals_check, warnings=warnings)
