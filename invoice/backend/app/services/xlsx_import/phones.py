"""Телефон получателя WhatsApp из xlsx (см. parsers/avantage.py) —
CounterpartyPhone, только когда для этого (trc_id, counterparty_id) там
ещё ничего нет.

"Только когда пусто" — тот же принцип, что уже применяется к телефону из
живого 1С в app/api/admin.py.counterparty_directory (докстринг
CounterpartyPhone: "значение из 1С — только подсказка при пустой записи...
сохранённое здесь значение админ может переопределить, и оно не
перезаписывается автоматически"). Здесь то же самое, просто источник
подсказки — xlsx, а не 1С: не различаем, кто раньше заполнил запись
(админ вручную, 1С-подсказка, эта же функция при прошлой загрузке) — раз
там уже что-то есть, не трогаем, независимо от источника.

CounterpartyPhone.trc_id, не tenant_id — телефоны получателей общие на
уровне ТЦ (см. модель), поэтому нужен tenant.trc_id, а не сам tenant_id."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.catalog import CounterpartyPhone, Tenant


def compute_phone_upserts(normalized_rows) -> dict[str, dict[str, Any]]:
    """Чистая функция (без БД, ради тестов) — cp_id -> {"phone",
    "counterparty_name"} для строк с непустым RawChargeRow.phone. Одна
    запись на контрагента — первое непустое значение среди повторов по
    типам начисления (rent/utilities/debt/other одного арендатора обычно
    несут один и тот же телефон)."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in normalized_rows:
        phone = getattr(row.source_row, "phone", None)
        if not phone:
            continue
        cp_id = row.counterparty_id
        if not cp_id or cp_id in by_id:
            continue
        by_id[cp_id] = {"phone": phone, "counterparty_name": row.ip_name}
    return by_id


def sync_xlsx_counterparty_phones(db: Session, tenant: Tenant, normalized_rows) -> int:
    """Возвращает число реально созданных строк CounterpartyPhone (не
    считает пропущенные из-за уже занятой записи)."""
    if not tenant.trc_id:
        return 0

    candidates = compute_phone_upserts(normalized_rows)
    if not candidates:
        return 0

    existing_ids = {
        cp_id.lower()
        for (cp_id,) in db.query(CounterpartyPhone.one_c_counterparty_id)
        .filter(CounterpartyPhone.trc_id == tenant.trc_id)
        .all()
    }

    created = 0
    for cp_id, info in candidates.items():
        if cp_id.lower() in existing_ids:
            continue
        db.add(
            CounterpartyPhone(
                trc_id=tenant.trc_id,
                one_c_counterparty_id=cp_id,
                counterparty_name=info["counterparty_name"],
                phone=info["phone"],
            )
        )
        created += 1

    if created:
        db.commit()
    return created
