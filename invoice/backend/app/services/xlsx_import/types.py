"""Общие типы xlsx-импорта. Слои (см. package docstring в __init__.py):

    parser (per-tenant)  ->  RawChargeRow
    normalize (общий)    ->  NormalizedRow
    upsert (общий)       ->  ImportSummary

RawChargeRow — «сырые» данные ровно как в файле, без единого решения
(матчинг/статус/service_type ещё не приняты). NormalizedRow — то же самое,
что производит normalize_1c_row для 1С-пути (см. payment_service.py) —
именно поэтому upsert один и тот же для обоих источников.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_
from typing import Optional


@dataclass(frozen=True)
class RawChargeRow:
    """Одна строка = один арендатор × один период × один тип начисления
    (Аренда/КУ/Долг/Прочее), взятая с листа "Начисление <месяц>" как есть."""

    raw_name: str
    period: str  # YYYY-MM
    charge_type: str  # "rent" | "utilities" | "debt" | "other"
    charged: float
    paid: float
    remainder: float
    brand: Optional[str] = None
    unit: Optional[str] = None  # "Помещ."
    zone: Optional[str] = None
    # БИН/ИИН арендатора, если файл его несёт (см. parsers/avantage.py) —
    # даёт normalize() матчинг понадёжнее, чем по имени (см.
    # counterparty_name_match.resolve_payment_counterparty_key). None у
    # парсеров, что эту колонку не читают (например maxi_mall) — БИН-матчинг
    # там просто не участвует, поведение не меняется.
    bin_value: Optional[str] = None
    # Телефон получателя WhatsApp, если файл его несёт (см.
    # parsers/avantage.py). Не участвует в матчинге (в отличие от
    # bin_value) — только заполняет CounterpartyPhone, когда там ещё пусто,
    # см. xlsx_import/phones.py. None у парсеров, что эту колонку не читают.
    phone: Optional[str] = None
    sheet_name: str = ""
    row_number: int = 0  # для диагностики/трассировки при ошибках парсинга
    # True — paid/remainder этой строки прочитаны из битой формулы (#REF! и
    # т.п.), а не из реального значения (см. parsers/avantage.py). 0 в
    # charged/paid/remainder тогда значит "неизвестно", не "ноль" — normalize
    # должен дать статус NEEDS_REVIEW, а не молча посчитать "оплачено".
    # Default False — существующие парсеры (maxi_mall) это поле не трогают.
    amounts_unreliable: bool = False


@dataclass(frozen=True)
class ParseResult:
    rows: list[RawChargeRow]
    periods: list[str]
    # period -> {"НАЧИСЛЕНО ok": bool, ...} — сверка суммы по каждому
    # (period, charge_type) с "Общий свод оплат", см. maxi_mall.py.
    totals_check: dict[str, dict]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedRow:
    """То, что реально идёт в upsert — тот же набор полей, что 1С-путь кладёт
    в TenantPayment (см. payment_service.sync_from_1c)."""

    tenant_id: int
    invoice_id: str  # синтетический, стабильный между перезаливками того же периода
    counterparty_id: str  # UUID из 1С или virtual:<hash> (см. counterparty_name_match.py)
    ip_name: str
    tenant_name: str
    invoice_date: date_
    due_date: date_
    period: str
    service_type: str
    amount: int  # начислено, тенге, округлено
    paid_amount: int
    status: str  # PaymentStatus.value
    matched: bool  # True — реальный counterparty_id из 1С, False — virtual:
    source_row: RawChargeRow


@dataclass(frozen=True)
class ImportSummary:
    tenant_id: int
    periods: list[str]
    rows_total: int
    rows_created: int
    rows_updated: int
    # Новый файл — полная замена xlsx-данных этого арендатора, не патч (см.
    # upsert.apply): всё, что было source="xlsx" у этого tenant_id и не
    # попало в текущую загрузку, удаляется. rows_deleted — сколько именно,
    # чтобы это было видно в ответе, а не молча происходило в фоне.
    rows_deleted: int
    rows_matched: int
    rows_unmatched: int
    unmatched_names: list[str]
    totals_check: dict[str, dict]
    warnings: list[str]
