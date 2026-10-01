"""RawChargeRow (сырое, per-parser) -> NormalizedRow (общее, готово к upsert).

Единственный слой, где принимаются решения: статус оплаты, матчинг
контрагента, синтетические id. Не знает ничего про формат конкретного ТЦ —
работает с уже разобранными RawChargeRow одинаково для любого парсера."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.catalog import Tenant
from app.models.counterparty_cache import CounterpartyCache
from app.models.payment import PaymentStatus
from app.services.counterparty_name_match import (
    build_bin_resolution_index,
    build_name_resolution_index,
    is_virtual_counterparty_id,
    resolve_payment_counterparty_key,
)
from app.services.invoice_service_type import _day_in_month, due_day_for_service_type
from app.services.payment_status_rules import PAID_TOLERANCE
from app.services.xlsx_import.types import NormalizedRow, RawChargeRow


def _status(raw: RawChargeRow, due_date: date, today: date) -> str:
    """По остатку, а не по пересчёту начислено-оплачено (см. types.py) —
    остаток уже посчитан в файле и корректно даёт "paid", когда остаток
    отрицательный (переплата/аванс с прошлого периода), в отличие от
    payment_coverage_status(charged, paid), который для отрицательного
    charged без специальной обработки посчитал бы это "не оплачено"
    (paid_enough требует paid>0 при amount<=0 — здесь amount может быть
    честно отрицательным, это не то же самое, что "нет начисления").

    overdue важнее суммы покрытия — тот же принцип, что
    PaymentService._row_coverage_status для 1С-строк.

    amounts_unreliable важнее всего остального: если paid/remainder в файле
    сами читались из битой формулы (см. RawChargeRow), 0 там — "неизвестно",
    а не "оплачено полностью" — раньше это молча садилось на PAID."""
    if raw.amounts_unreliable:
        return PaymentStatus.NEEDS_REVIEW.value
    if raw.remainder <= PAID_TOLERANCE:
        return PaymentStatus.PAID.value
    if due_date < today:
        return PaymentStatus.OVERDUE.value
    if raw.paid > 0:
        return PaymentStatus.PARTIAL.value
    return PaymentStatus.UNPAID.value


def _load_counterparty_cache_data(db: Session, tenant_id: int) -> list[dict]:
    """Отдельная функция (не инлайн в normalize()) специально ради тестов —
    CounterpartyCache.data — Postgres-only JSONB, не рендерится на in-memory
    SQLite, которую использует тестовый conftest.py (см. её же комментарий
    там). Тесты normalize() патчат эту функцию вместо реальной БД-строки,
    как _counterparty_meta_index уже патчится в тестах payment_service."""
    cache_row = db.query(CounterpartyCache).filter(CounterpartyCache.tenant_id == tenant_id).first()
    return list(cache_row.data or []) if cache_row and cache_row.data else []


def normalize(
    db: Session,
    tenant: Tenant,
    raw_rows: list[RawChargeRow],
    *,
    today: Optional[date] = None,
) -> list[NormalizedRow]:
    today = today or date.today()

    cache_data = _load_counterparty_cache_data(db, tenant.id)
    name_index = build_name_resolution_index(cache_data)
    bin_index = build_bin_resolution_index(cache_data)
    cache_names_by_id = {
        str(cp.get("id") or "").strip().lower(): str(cp.get("fullName") or "")
        for cp in cache_data
    }

    rent_due_day = int(getattr(tenant, "invoice_due_day", None) or 5)
    utilities_due_day = int(getattr(tenant, "invoice_due_day_utilities", None) or rent_due_day)
    operations_due_day = int(getattr(tenant, "invoice_due_day_operations", None) or rent_due_day)

    out: list[NormalizedRow] = []
    for raw in raw_rows:
        cp_key, display_name = resolve_payment_counterparty_key(
            counterparty_id=None,
            tenant_name=raw.raw_name,
            name_index=name_index,
            cache_names_by_id=cache_names_by_id,
            bin_index=bin_index,
            bin_value=raw.bin_value,
        )
        if not cp_key:
            # Пустое имя после нормализации — реально пустая строка, пропускаем.
            continue
        matched = not is_virtual_counterparty_id(cp_key)

        year, month = int(raw.period[:4]), int(raw.period[5:7])
        invoice_date = date(year, month, 1)
        due_day = due_day_for_service_type(
            raw.charge_type, rent=rent_due_day, utilities=utilities_due_day, operations=operations_due_day
        )
        due_date = _day_in_month(year, month, due_day)

        status = _status(raw, due_date, today)
        display = display_name or raw.raw_name

        out.append(
            NormalizedRow(
                tenant_id=tenant.id,
                invoice_id=f"xlsx:{tenant.id}:{raw.period}:{cp_key}:{raw.charge_type}",
                counterparty_id=cp_key,
                ip_name=display,
                tenant_name=display,
                invoice_date=invoice_date,
                due_date=due_date,
                period=raw.period,
                service_type=raw.charge_type,
                amount=round(raw.charged),
                paid_amount=round(raw.paid),
                status=status,
                matched=matched,
                source_row=raw,
            )
        )
    return out
