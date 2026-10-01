"""Долг/Аванс/Нетто (CounterpartyBalance) из уже загруженных xlsx-строк —
excel-файлы вроде Maxi Mall уже дают остаток по каждому контрагенту в
листах "Начисление", отдельного источника для баланса не нужно.

Считается по ВСЕМ tenant_payments(source="xlsx") этого арендатора/
контрагента, не только по строкам последней загрузки — повторная загрузка
файла с новым месяцем должна прибавляться к общей картине, а не заменять
её только текущим периодом.

Пишет с source="xlsx" — counterparty_balance_service.replace_balances_for_tenant
(1С-синк) эти строки не трогает, см. его докстринг.

Запускается ПОСЛЕ upsert.apply() (см. __init__.py), т.е. после того, как
устаревшие source="xlsx" строки tenant_payments уже удалены (полная замена,
см. upsert.py) — так что "какие counterparty_id сейчас реально есть"
пересчитывается каждый раз с нуля из актуального состояния. Раньше здесь
была та же дыра, что чинит upsert.py: контрагент, у которого не осталось ни
одной xlsx-строки после переключения файла, продолжал висеть в
CounterpartyBalance с прошлым долгом/авансом навсегда."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.counterparty_balance import CounterpartyBalance
from app.models.payment import TenantPayment


def recompute_xlsx_balances(db: Session, tenant_id: int) -> int:
    """debit = должны нам (остаток > 0), credit = аванс/переплата (остаток < 0)
    — тот же знак-в-две-корзины, что и у 1С-баланса (см. CounterpartyBalance
    docstring), посчитанный из amount-paid_amount по каждой xlsx-строке."""
    rows = (
        db.query(
            TenantPayment.counterparty_id,
            func.max(TenantPayment.tenant_name).label("name"),
            func.sum(TenantPayment.amount).label("total_amount"),
            func.sum(TenantPayment.paid_amount).label("total_paid"),
        )
        .filter(
            TenantPayment.tenant_id == tenant_id,
            TenantPayment.source == "xlsx",
            TenantPayment.counterparty_id.isnot(None),
            TenantPayment.counterparty_id != "",
        )
        .group_by(TenantPayment.counterparty_id)
        .all()
    )

    now = datetime.now(timezone.utc)
    saved = 0
    touched_cp_ids: set[str] = set()
    for cp_id, name, total_amount, total_paid in rows:
        touched_cp_ids.add(cp_id)
        remainder = Decimal(str(total_amount or 0)) - Decimal(str(total_paid or 0))
        debit = remainder if remainder > 0 else Decimal("0")
        credit = -remainder if remainder < 0 else Decimal("0")

        existing = (
            db.query(CounterpartyBalance)
            .filter(
                CounterpartyBalance.tenant_id == tenant_id,
                CounterpartyBalance.counterparty_id == cp_id,
            )
            .first()
        )
        if existing:
            existing.counterparty_name = name or existing.counterparty_name
            existing.debit = debit
            existing.credit = credit
            existing.source = "xlsx"
            existing.synced_at = now
        else:
            db.add(
                CounterpartyBalance(
                    tenant_id=tenant_id,
                    counterparty_id=cp_id,
                    counterparty_name=name,
                    debit=debit,
                    credit=credit,
                    source="xlsx",
                    synced_at=now,
                )
            )
        saved += 1

    # Контрагент, у которого не осталось ни одной source="xlsx" строки в
    # tenant_payments (счёты этого арендатора/контрагента заменены новым
    # файлом или новый файл вообще про других контрагентов), не должен
    # продолжать висеть здесь со старым долгом/авансом.
    (
        db.query(CounterpartyBalance)
        .filter(
            CounterpartyBalance.tenant_id == tenant_id,
            CounterpartyBalance.source == "xlsx",
            ~CounterpartyBalance.counterparty_id.in_(touched_cp_ids),
        )
        .delete(synchronize_session=False)
    )

    db.commit()
    return saved
