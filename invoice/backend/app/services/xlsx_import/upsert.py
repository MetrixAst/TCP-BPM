"""NormalizedRow -> TenantPayment. Тот же upsert-контракт, что и 1С-путь
(payment_service.sync_from_1c): найти существующую строку по invoice_id
(case-insensitive) в рамках tenant_id, обновить или создать, source="xlsx".

invoice_id синтетический и всегда с префиксом "xlsx:" (см. normalize.py) —
пересечься с 1С-invoice_id (GUID/число) не может, поэтому, в отличие от
1С-пути, доп. фильтр по source для поиска существующей строки не нужен:
префикс уже гарантирует, что найдётся только наша же строка от прошлой
загрузки этого периода, а не что-то из 1С.

Каждая загрузка — ПОЛНАЯ ЗАМЕНА xlsx-данных этого арендатора, не патч
(живой баг, 2026-08-28: арендатора сначала залили файлом на ~150 строк,
потом файлом другого формата на 10 строк — старые 150 остались в базе
навсегда, upsert их просто никогда не трогал). Поэтому после апсерта всё
source="xlsx" у этого tenant_id, чего не было в текущей загрузке,
удаляется (см. ниже). Единственное исключение — новая загрузка дала 0
строк: это почти всегда испорченный/не тот файл (см.
app/api/xlsx_import.py), а не намеренная команда "очистить всё"; в этом
случае существующие данные не трогаем вообще."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.payment import PaymentStatus, TenantPayment
from app.services.xlsx_import.types import ImportSummary, NormalizedRow


def apply(
    db: Session,
    tenant_id: int,
    normalized_rows: list[NormalizedRow],
    *,
    periods: list[str],
    totals_check: dict,
    warnings: list[str],
) -> ImportSummary:
    created = updated = 0
    matched = unmatched = 0
    unmatched_names: list[str] = []
    touched_ids: set[str] = set()

    for row in normalized_rows:
        inv_key = row.invoice_id.lower()
        touched_ids.add(inv_key)
        existing = (
            db.query(TenantPayment)
            .filter(
                func.lower(TenantPayment.invoice_id) == inv_key,
                TenantPayment.tenant_id == tenant_id,
            )
            .first()
        )

        if existing:
            existing.ip_name = row.ip_name
            existing.tenant_name = row.tenant_name
            existing.invoice_date = row.invoice_date
            existing.due_date = row.due_date
            existing.status = PaymentStatus(row.status)
            existing.period = row.period
            existing.amount = row.amount
            existing.paid_amount = row.paid_amount
            existing.counterparty_id = row.counterparty_id
            existing.service_type = row.service_type
            existing.source = "xlsx"
            updated += 1
        else:
            db.add(
                TenantPayment(
                    tenant_id=tenant_id,
                    ip_name=row.ip_name,
                    tenant_name=row.tenant_name,
                    invoice_date=row.invoice_date,
                    due_date=row.due_date,
                    status=PaymentStatus(row.status),
                    period=row.period,
                    amount=row.amount,
                    paid_amount=row.paid_amount,
                    invoice_id=row.invoice_id,
                    counterparty_id=row.counterparty_id,
                    service_type=row.service_type,
                    source="xlsx",
                )
            )
            created += 1

        if row.matched:
            matched += 1
        else:
            unmatched += 1
            if row.ip_name not in unmatched_names:
                unmatched_names.append(row.ip_name)

    deleted = 0
    if touched_ids:
        deleted = (
            db.query(TenantPayment)
            .filter(
                TenantPayment.tenant_id == tenant_id,
                TenantPayment.source == "xlsx",
                ~func.lower(TenantPayment.invoice_id).in_(touched_ids),
            )
            .delete(synchronize_session=False)
        )
    else:
        # 0 строк в новой загрузке. Не удаляем ничего — см. модульный
        # докстринг про почему, — но если у арендатора уже есть xlsx-данные
        # от прошлой загрузки, явно скажем, что они не тронуты: иначе "0
        # rows, warnings объясняют формат" выглядит как норм ответ, а не как
        # "твои старые счета всё ещё там, но не заменены".
        has_existing = (
            db.query(TenantPayment.id)
            .filter(TenantPayment.tenant_id == tenant_id, TenantPayment.source == "xlsx")
            .first()
            is not None
        )
        if has_existing:
            warnings = list(warnings) + [
                "Файл дал 0 строк — данные этого арендатора от предыдущей загрузки НЕ удалены "
                "и НЕ заменены (полная замена происходит только когда новый файл даёт хотя бы "
                "одну строку)"
            ]

    db.commit()

    return ImportSummary(
        tenant_id=tenant_id,
        periods=periods,
        rows_total=len(normalized_rows),
        rows_created=created,
        rows_updated=updated,
        rows_deleted=deleted,
        rows_matched=matched,
        rows_unmatched=unmatched,
        unmatched_names=unmatched_names,
        totals_check=totals_check,
        warnings=warnings,
    )
