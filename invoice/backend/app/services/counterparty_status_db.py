from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.payment import TenantPayment
from app.services.counterparty_name_match import (
    load_cache_name_maps,
    resolve_payment_counterparty_key,
)
from app.services.payment_status_rules import payment_coverage_status
from app.services.xlsx_import.precedence import exclude_shadowed_one_c_rows


def _payment_row_status(row: TenantPayment) -> str:
    """paid/partial/unpaid/overdue по покрытию суммы — как в PaymentService.
    _row_coverage_status; сохранённая колонка status не пересчитывается между
    синками, поэтому не источник истины для paid/partial/unpaid."""
    stored = (
        row.status.value if hasattr(row.status, "value") else str(row.status or "")
    ).lower()
    if stored == "overdue":
        return stored
    if row.amount is not None and row.paid_amount is not None:
        return payment_coverage_status(row.amount, row.paid_amount)
    if row.paid_at:
        return "paid"
    return stored or "unpaid"


def _invoice_payload_from_row(row: TenantPayment, display_name: str) -> dict[str, Any]:
    status = _payment_row_status(row)
    return {
        "invoiceId": row.invoice_id,
        "invoiceNumber": None,
        "invoiceDate": (
            row.invoice_date.isoformat()
            if row.invoice_date
            else (row.due_date.isoformat() if row.due_date else None)
        ),
        "dueDate": row.due_date.isoformat() if row.due_date else None,
        "documentStatus": "posted",
        "paymentStatus": status,
        "paidAt": row.paid_at.isoformat() if row.paid_at else None,
        "amount": row.amount,
        "paidAmount": row.paid_amount if row.paid_amount is not None else (row.amount if status == "paid" else None),
        "counterpartyName": display_name,
    }


def _load_cache_data(db: Session, tenant_id: Optional[int]) -> list[dict[str, Any]]:
    if not tenant_id:
        return []
    from app.models.counterparty_cache import CounterpartyCache

    cache_row = (
        db.query(CounterpartyCache)
        .filter(CounterpartyCache.tenant_id == tenant_id)
        .first()
    )
    if not cache_row or not cache_row.data:
        return []
    return list(cache_row.data)


# Приоритет счёта на контрагента в реестре, когда счетов за период несколько:
# самый проблемный/срочный важнее, а не просто самый свежий по дате — иначе
# просроченный/частично оплаченный счёт может заслониться более новым оплаченным.
_STATUS_PRIORITY = {"overdue": 3, "partial": 2, "unpaid": 1, "paid": 0}


def latest_invoice_status_by_counterparty_from_db(
    db: Session,
    *,
    tenant_id: Optional[int],
    period: Optional[str],
) -> dict[str, dict]:
    """Самый срочный счёт за период по контрагенту (UUID, сопоставление по имени или virtual:…).

    Приоритет: overdue > partial > unpaid > paid; при равном статусе — более
    свежий по дате счёта."""
    query = db.query(TenantPayment).filter(
        TenantPayment.invoice_id.isnot(None),
        TenantPayment.invoice_id != "",
    )
    if period:
        query = query.filter(TenantPayment.period == period)
    if tenant_id:
        # tenant_id (FK), не ip_name==legal_name — см. аудит от 2026-08-25.
        query = query.filter(TenantPayment.tenant_id == tenant_id)
        # prefer_xlsx: без этого — 1С-строка того же счёта может выиграть по
        # приоритету статуса (overdue > partial > ...) у более свежей
        # xlsx-строки, и "самый срочный счёт" контрагента покажет устаревший
        # статус из 1С поверх верного из excel (см. precedence.py).
        query = exclude_shadowed_one_c_rows(db, query, tenant_id)

    rows = query.order_by(
        TenantPayment.invoice_date.desc(),
        TenantPayment.id.desc(),
    ).all()

    cache_data = _load_cache_data(db, tenant_id)
    name_index, names_by_id = load_cache_name_maps(cache_data)

    best_row: dict[str, TenantPayment] = {}
    best_key: dict[str, tuple] = {}
    best_name: dict[str, str] = {}
    for row in rows:
        cp_key, display_name = resolve_payment_counterparty_key(
            counterparty_id=row.counterparty_id,
            tenant_name=row.tenant_name,
            name_index=name_index,
            cache_names_by_id=names_by_id,
        )
        if not cp_key:
            continue
        status = _payment_row_status(row)
        priority = _STATUS_PRIORITY.get(status, 1)
        sort_key = (priority, row.invoice_date or row.due_date, row.id)
        if cp_key not in best_key or sort_key > best_key[cp_key]:
            best_key[cp_key] = sort_key
            best_row[cp_key] = row
            best_name[cp_key] = display_name

    return {
        cp_key: _invoice_payload_from_row(row, best_name[cp_key])
        for cp_key, row in best_row.items()
    }


def invoice_counts_by_counterparty_from_db(
    db: Session,
    *,
    tenant_id: Optional[int],
    period: Optional[str],
) -> dict[str, int]:
    from collections import defaultdict

    query = db.query(TenantPayment).filter(
        TenantPayment.invoice_id.isnot(None),
        TenantPayment.invoice_id != "",
    )
    if period:
        query = query.filter(TenantPayment.period == period)
    if tenant_id:
        # tenant_id (FK), не ip_name==legal_name — см. аудит от 2026-08-25.
        query = query.filter(TenantPayment.tenant_id == tenant_id)
        # prefer_xlsx: без этого — 1С-строка того же счёта может выиграть по
        # приоритету статуса (overdue > partial > ...) у более свежей
        # xlsx-строки, и "самый срочный счёт" контрагента покажет устаревший
        # статус из 1С поверх верного из excel (см. precedence.py).
        query = exclude_shadowed_one_c_rows(db, query, tenant_id)

    cache_data = _load_cache_data(db, tenant_id)
    name_index, names_by_id = load_cache_name_maps(cache_data)

    counts: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for row in query.all():
        inv_key = (row.invoice_id or "").strip().lower()
        cp_key, _ = resolve_payment_counterparty_key(
            counterparty_id=row.counterparty_id,
            tenant_name=row.tenant_name,
            name_index=name_index,
            cache_names_by_id=names_by_id,
        )
        if not cp_key or not inv_key:
            continue
        dedupe_key = f"{cp_key}:{inv_key}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        counts[cp_key] += 1
    return dict(counts)
