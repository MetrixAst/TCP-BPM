"""Парсер под файл ТРЦ Avantage (mock-версия разобрана 2026-08-27, реальный
файл ещё не видели — см. app/services/xlsx_import/registry.py про то, что
ключ парсера — свойство формата файла, не арендатора).

Формат отличается от Maxi Mall (parsers/maxi_mall.py) в двух вещах, из-за
которых он не влезает в тот парсер как есть:
- Один лист на файл (у выгрузки, что видели, назывался "Sheet1", но это не
  гарантировано — период и вовсе не в имени листа) с периодом внутри
  заголовка (ячейка A1, например "...— АВГУСТ 2026"), а не отдельный лист
  "Начисление <МЕСЯЦ>" на каждый период, как у Maxi Mall. Поэтому лист с
  начислениями ищем по тексту заголовка ("начисление" в A1), а не по имени
  листа/префиксу.
- Нет листа "Общий свод оплат" — самопроверки суммы (totals_check) для
  этого формата пока нет; totals_check всегда пустой.

Таблица начислений (строка заголовков, типы аренда/КУ/долг/прочее ×
начислено/оплачено/остаток) совпадает по словарю заголовков с Maxi Mall —
это похоже на общий жаргон бухгалтерии ТЦ, а не совпадение. Тем не менее
классификация колонок реализована здесь самостоятельно (не импортируется
из maxi_mall.py) — по духу registry.py "новый ТЦ = новый модуль, ядро не
трогается", per-tenant парсеры друг от друга не зависят.

БИН и номер телефона арендатора: подписаны "Бик"/"номер телефона" в
групповой строке 2 (без своей подписи в строке 3, где типы начислений).
БИН даёт normalize() матчинг понадёжнее, чем по имени (см.
RawChargeRow.bin_value, counterparty_name_match.
resolve_payment_counterparty_key). Телефон нигде не матчится — только
заполняет CounterpartyPhone, если там ещё пусто, см.
xlsx_import/phones.py — чтобы WhatsApp/Green API можно было сразу
тестировать без ручного ввода номеров в админке. Специально только здесь — maxi_mall.py не трогаем, там БИН на
реальном файле не проверялся (см. отдельный вопрос владельцу данных Maxi
Mall про "% с обор./Прочее ₸").

Важная находка на реальном mock-файле: колонки "оплачено"/"остаток" были
битой формулой (#REF!) на КАЖДОЙ строке — то есть 1С/Excel-эталон, из
которого файл собирали, ссылался на данные, которых в этой копии не было.
_cell_float трактует это как 0.0 (иначе всё падает), но 0.0 — это НЕ "ничего
не оплачено", это "неизвестно". Поэтому такие ячейки размечаются отдельно
и по ним добавляется предупреждение, а не молчаливый 0."""
from __future__ import annotations

import re
from typing import Optional

from openpyxl import load_workbook

from app.services.xlsx_import.types import ParseResult, RawChargeRow

_HEADER_ROW = 3
_DATA_START_ROW = 4

_MONTHS_RU = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
_MONTH_PATTERN = re.compile(
    r"(" + "|".join(_MONTHS_RU) + r")\s+(20\d{2})", re.IGNORECASE
)

# Порог "это ноль" — см. тот же допуск в maxi_mall.py: строка создаётся,
# только если хотя бы одно из начислено/оплачено/остаток реально ненулевое.
_ZERO_EPS = 0.01

# Excel хранит ошибку формулы как обычную строку в кэшированном значении
# ("#REF!", "#DIV/0!", "#N/A", "#VALUE!", "#NAME?", "#NULL!") — отличаем от
# просто нечисловой ерунды по этому маркеру, а не бросаем исключение.
_FORMULA_ERROR_RE = re.compile(r"^#[A-Z/]+[!?]?$")

PARSER_KEY = "avantage"


def _normalize_header(raw: object) -> str:
    return " ".join(str(raw or "").replace("\n", " ").lower().split())


def _classify_headers(ws, header_row: int) -> dict:
    name_col = unit_col = brand_col = zone_col = bin_col = phone_col = None
    charges: dict[tuple[str, str], int] = {}

    for col in range(1, ws.max_column + 1):
        header = _normalize_header(ws.cell(row=header_row, column=col).value)
        if not header:
            # "Бик"/"номер телефона" в реальном mock-файле не имеют своей
            # подписи в строке с типами начислений вообще — подпись только в
            # групповой строке 2 ("◀ НАЧИСЛЕНО ▶" и т.п., см. модульный
            # докстринг). Смотрим туда только когда header_row для этой
            # колонки пуст — не переопределяет обычную классификацию выше.
            group_header = _normalize_header(ws.cell(row=2, column=col).value)
            if "бик" in group_header or "бин" in group_header:
                bin_col = col
            elif "телефон" in group_header:
                phone_col = col
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
        elif re.search(r"\bост\b", header) or header.endswith("ост. ₸"):
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
        "bin_col": bin_col,
        "phone_col": phone_col,
        "charges": charges,
    }


def _is_charge_sheet_title(title_cell: object) -> bool:
    return "начисление" in str(title_cell or "").lower()


def _extract_period(title_cell: object) -> Optional[str]:
    match = _MONTH_PATTERN.search(str(title_cell or ""))
    if not match:
        return None
    month_num = _MONTHS_RU[match.group(1).lower()]
    year = match.group(2)
    return f"{year}-{month_num:02d}"


def _find_note(ws) -> Optional[str]:
    """Свободный текст, что ТЦ иногда дописывает в ту же строку заголовка
    (например "А - сентябрь, КУ - июль" — период по конкретному типу
    начисления расходится с общим периодом в A1). Формат ячейки не
    зафиксирован ни разу, поэтому здесь только сигнал наружу через
    warnings, структурного разбора нет — читающий отчёт решает сам."""
    for col in range(2, ws.max_column + 1):
        value = ws.cell(row=1, column=col).value
        if value and str(value).strip():
            return str(value).strip()
    return None


def _cell_float(ws, row: int, col: Optional[int]) -> tuple[float, bool]:
    """Возвращает (значение, is_formula_error). Битая формула (#REF! и
    т.п.) читается как 0.0, но помечается — это не то же самое, что
    настоящий ноль в файле."""
    if col is None:
        return 0.0, False
    val = ws.cell(row=row, column=col).value
    if val is None:
        return 0.0, False
    if isinstance(val, str) and _FORMULA_ERROR_RE.match(val.strip()):
        return 0.0, True
    try:
        return float(val), False
    except (TypeError, ValueError):
        return 0.0, False


def _is_zero(*values: float) -> bool:
    return all(abs(v) < _ZERO_EPS for v in values)


def _cell_numeric_string(ws, row: int, col: Optional[int]) -> Optional[str]:
    """БИН и номер телефона приходят из Excel как float (123456781233.0,
    77475424201.0), не строка — нельзя просто str(val), получится
    "...233.0". int()-круглим только целые значения; нецелое здесь значит
    не БИН/телефон, а что-то не то в колонке. Общая для обеих колонок —
    одна и та же проблема формата, не совпадение семантики."""
    if col is None:
        return None
    val = ws.cell(row=row, column=col).value
    if val is None:
        return None
    if isinstance(val, float):
        return str(int(val)) if val.is_integer() else None
    text = str(val).strip()
    return text or None


def _parse_charge_sheet(ws, sheet_name: str, period: str, warnings: list[str]) -> list[RawChargeRow]:
    header_map = _classify_headers(ws, _HEADER_ROW)
    rows: list[RawChargeRow] = []
    error_cells = 0

    for row_num in range(_DATA_START_ROW, ws.max_row + 1):
        raw_name = ws.cell(row=row_num, column=header_map["name_col"]).value
        if raw_name is None or not str(raw_name).strip():
            continue
        name = str(raw_name).strip()
        if name.lower().startswith("итого"):
            continue

        brand = ws.cell(row=row_num, column=header_map["brand_col"]).value if header_map["brand_col"] else None
        unit = ws.cell(row=row_num, column=header_map["unit_col"]).value if header_map["unit_col"] else None
        zone = ws.cell(row=row_num, column=header_map["zone_col"]).value if header_map["zone_col"] else None
        bin_value = _cell_numeric_string(ws, row_num, header_map["bin_col"])
        phone_value = _cell_numeric_string(ws, row_num, header_map["phone_col"])

        for metric in ("rent", "utilities", "debt", "other"):
            charged, charged_err = _cell_float(ws, row_num, header_map["charges"].get((metric, "charged")))
            paid, paid_err = _cell_float(ws, row_num, header_map["charges"].get((metric, "paid")))
            remainder, rem_err = _cell_float(ws, row_num, header_map["charges"].get((metric, "remainder")))
            row_has_error = charged_err or paid_err or rem_err
            error_cells += sum((charged_err, paid_err, rem_err))
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
                    bin_value=bin_value,
                    phone=phone_value,
                    sheet_name=sheet_name,
                    row_number=row_num,
                    amounts_unreliable=row_has_error,
                )
            )

    if not rows:
        warnings.append(f'Лист "{sheet_name}": ни одной строки с данными не найдено')
    if error_cells:
        warnings.append(
            f'Лист "{sheet_name}": {error_cells} ячеек с битой формулой (#REF!/аналог) в столбцах '
            f'"оплачено"/"остаток" прочитаны как 0 — реальные суммы оплаты/остатка из файла неизвестны, '
            f'нужно поправить формулы в источнике до перезаливки'
        )

    return rows


def parse(file_bytes: bytes) -> ParseResult:
    wb = load_workbook(filename=__import__("io").BytesIO(file_bytes), data_only=True)

    all_rows: list[RawChargeRow] = []
    periods: list[str] = []
    warnings: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        title_cell = ws.cell(row=1, column=1).value
        if not _is_charge_sheet_title(title_cell):
            continue

        period = _extract_period(title_cell)
        if not period:
            warnings.append(f'Лист "{sheet_name}": не удалось определить период (месяц/год) из заголовка A1')
            continue
        periods.append(period)

        note = _find_note(ws)
        if note:
            warnings.append(
                f'Лист "{sheet_name}": примечание в заголовке — "{note}" — период по отдельным типам '
                f'начисления может отличаться от {period}, проверить вручную'
            )

        all_rows.extend(_parse_charge_sheet(ws, sheet_name, period, warnings))

    if not periods:
        warnings.append('Ни одного листа с начислениями не найдено (ожидался заголовок A1 со словом "начисление")')

    # Нет листа "Общий свод оплат" в этом формате — самопроверки суммы, как
    # у Maxi Mall (см. parsers/maxi_mall.py), для Avantage пока нет.
    return ParseResult(rows=all_rows, periods=periods, totals_check={}, warnings=warnings)
