"""Объединённый журнал WhatsApp-отправок: Notification (ручные/массовые) + AutoNotificationLog (авто).

Не покрывает /api/notifications/send-file — тот путь пишет только
CounterpartyPhone.last_whatsapp_sent_at, без записи в любую из этих таблиц.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.auto_notification_log import AutoNotificationLog
from app.models.catalog import Tenant
from app.models.notification import Notification
from app.models.payment import TenantPayment

# trigger_kind (auto) -> тот же бакет NotificationType, что и у ручных отправок.
# Смещения совпадают с _REMINDER_OFFSETS_TO_TYPE в auto_notification_service.py
# (-5/-3/0/+1/+3/+5); "before7"/"after7"/"before1" оставлены для чтения
# исторических записей, созданных до смены схемы смещений.
_TRIGGER_PREFIX_TO_TYPE = {
    "before7": "week_before",
    "before5": "week_before",
    "before3": "three_days",
    "before1": "three_days",
    "dueday": "same_day",
    "after1": "overdue",
    "after3": "overdue",
    "after5": "overdue",
    "after7": "overdue",
}


def _trigger_kind_to_notification_type(trigger_kind: str) -> Optional[str]:
    prefix = (trigger_kind or "").split("_", 1)[0]
    return _TRIGGER_PREFIX_TO_TYPE.get(prefix)


def _scoped_tenants(db: Session, trc_id: int, tenant_id: Optional[int]) -> list[Tenant]:
    query = db.query(Tenant).filter(Tenant.trc_id == trc_id)
    if tenant_id:
        query = query.filter(Tenant.id == tenant_id)
    return query.all()


def _manual_query(db: Session, tenants: list[Tenant], date_from: Optional[date], date_to: Optional[date]):
    # tenant_id (FK), не ip_name.in_(legal_names) — legal_name не уникален
    # между арендаторами, см. аудит от 2026-08-25.
    tenant_ids = [t.id for t in tenants]
    if not tenant_ids:
        return None
    query = (
        db.query(Notification, TenantPayment)
        .join(TenantPayment, Notification.payment_id == TenantPayment.id)
        .filter(TenantPayment.tenant_id.in_(tenant_ids))
    )
    if date_from:
        query = query.filter(func.date(Notification.sent_at) >= date_from)
    if date_to:
        query = query.filter(func.date(Notification.sent_at) <= date_to)
    return query


def _auto_query(db: Session, tenants: list[Tenant], date_from: Optional[date], date_to: Optional[date]):
    tenant_ids = [t.id for t in tenants]
    if not tenant_ids:
        return None
    query = (
        db.query(AutoNotificationLog, TenantPayment)
        .outerjoin(
            TenantPayment,
            func.lower(TenantPayment.invoice_id) == func.lower(AutoNotificationLog.invoice_id),
        )
        .filter(AutoNotificationLog.tenant_id.in_(tenant_ids))
        # Both bulk_debtor_notify_service ("bulk_<дата>") and
        # xlsx_bulk_notify_service ("xlsx_bulk_<дата>", added 2026-09-02)
        # reuse this table purely as a same-day duplicate-send guard — the
        # actual delivery record for that send already exists as a
        # Notification row (picked up by _manual_query), so these guard-only
        # rows would otherwise show up twice. "%bulk_%" (not "bulk_%")
        # catches both prefixes in one pattern; no other trigger_kind this
        # table holds (before5_/dueday_/after1_/... from auto-notify)
        # contains "bulk_" anywhere.
        .filter(~AutoNotificationLog.trigger_kind.like("%bulk\\_%", escape="\\"))
    )
    if date_from:
        query = query.filter(func.date(AutoNotificationLog.sent_at) >= date_from)
    if date_to:
        query = query.filter(func.date(AutoNotificationLog.sent_at) <= date_to)
    return query


def _manual_row_to_entry(notification: Notification, payment: Optional[TenantPayment]) -> dict[str, Any]:
    return {
        "source": "manual",
        "sent_at": notification.sent_at,
        "phone_number": notification.phone_number,
        "counterparty_name": payment.tenant_name if payment else None,
        "ip_name": payment.ip_name if payment else None,
        "invoice_id": payment.invoice_id if payment else None,
        "notification_type": notification.notification_type.value
        if notification.notification_type
        else None,
        "service_type": None,
        "status": notification.status.value if notification.status else None,
    }


def _auto_row_to_entry(log: AutoNotificationLog, payment: Optional[TenantPayment]) -> dict[str, Any]:
    return {
        "source": "auto",
        "sent_at": log.sent_at,
        "phone_number": log.phone_number,
        "counterparty_name": (payment.tenant_name if payment else None) or None,
        "ip_name": payment.ip_name if payment else None,
        "invoice_id": log.invoice_id,
        "notification_type": _trigger_kind_to_notification_type(log.trigger_kind),
        "service_type": log.service_type,
        "status": None,
    }


def get_whatsapp_log(
    db: Session,
    *,
    trc_id: int,
    tenant_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    tenants = _scoped_tenants(db, trc_id, tenant_id)
    if not tenants:
        return [], 0

    manual_query = _manual_query(db, tenants, date_from, date_to)
    auto_query = _auto_query(db, tenants, date_from, date_to)

    total = 0
    if manual_query is not None:
        total += manual_query.count()
    if auto_query is not None:
        total += auto_query.count()

    # Fetch enough of each side (offset+limit) to guarantee correct merged
    # ordering after sort — see plan doc for the tradeoff vs. a real SQL UNION.
    fetch_n = offset + limit
    entries: list[dict[str, Any]] = []
    if manual_query is not None:
        rows = manual_query.order_by(Notification.sent_at.desc()).limit(fetch_n).all()
        entries.extend(_manual_row_to_entry(n, p) for n, p in rows)
    if auto_query is not None:
        rows = auto_query.order_by(AutoNotificationLog.sent_at.desc()).limit(fetch_n).all()
        entries.extend(_auto_row_to_entry(log, p) for log, p in rows)

    entries.sort(key=lambda e: e["sent_at"] or datetime.min, reverse=True)
    page = entries[offset : offset + limit]
    return page, total
