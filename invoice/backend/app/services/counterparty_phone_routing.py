"""Выбор номера WhatsApp для аренды / коммуналки / эксплуатации и маркетинга."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.catalog import CounterpartyPhone
from app.services.invoice_service_type import ServiceType
from app.services.phone_list import split_phone_values


def resolve_phone_for_service(
    row: Optional[CounterpartyPhone],
    service_type: ServiceType,
    fallback_phones: Optional[List[str]] = None,
) -> Optional[str]:
    phones = split_phone_values(row.phone) if row and row.phone else list(fallback_phones or [])
    if not phones:
        return None

    if row:
        if service_type == "rent" and row.phone_rent:
            return row.phone_rent.strip()
        if service_type == "utilities" and row.phone_utilities:
            return row.phone_utilities.strip()
        if service_type == "operations" and row.phone_operations:
            return row.phone_operations.strip()

    if len(phones) == 1:
        return phones[0]

    if service_type == "rent":
        return phones[0]
    if service_type == "utilities":
        return phones[1] if len(phones) > 1 else phones[0]
    if service_type == "operations":
        return phones[2] if len(phones) > 2 else phones[0]
    return phones[0]


def mark_counterparty_whatsapp_sent(
    db: Session,
    *,
    trc_id: Optional[int],
    counterparty_id: Optional[str],
    when: Optional[datetime] = None,
) -> bool:
    """Проставить last_whatsapp_sent_at контрагенту — любая успешная отправка
    (ручная, массовая, авто-рассылка, файл). Не создаёт запись, если её ещё
    нет (нечего трогать — телефон контрагента не сохранён в админке)."""
    cp_id = (counterparty_id or "").strip()
    if not trc_id or not cp_id:
        return False
    row = (
        db.query(CounterpartyPhone)
        .filter(
            CounterpartyPhone.trc_id == trc_id,
            CounterpartyPhone.one_c_counterparty_id.ilike(cp_id),
        )
        .first()
    )
    if not row:
        return False
    row.last_whatsapp_sent_at = when or datetime.utcnow()
    db.commit()
    return True
