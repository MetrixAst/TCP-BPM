"""Bulk WhatsApp send for xlsx-imported invoices (TenantPayment source="xlsx").

Deliberately a SEPARATE module from bulk_debtor_notify_service.py, not a
branch inside it — that function is built entirely around live 1C
(hard-stops if `not integration.client`, derives service_type per invoice
via a live `invoice_service_types_from_1c` call). Bolting an xlsx branch
into it would risk the already-correct, already-tested 1C path for every
other TRC using it. This module never makes a single live 1C call — see
xlsx_invoice_pdf.py's own docstring for why an xlsx row's synthetic
"xlsx:..." id can never be resolved through anything 1C-shaped anyway.

Built 2026-09-01 for a concrete deadline: Maxi Mall (~150 tenants) needs
their September rent invoices sent from an Excel file, and sending them
one by one through the single-send endpoint (app/api/notifications.py)
is not realistic at that scale. Mirrors bulk_debtor_notify_service.py's
idempotency mechanism (reserve_send_slot / AutoNotificationLog, the same
table and unique constraint the 1C bulk path and auto-notify already
share — a re-run with the same trigger_kind on the same day never
double-sends) and its "don't let one bad row kill the batch" error
handling, but everything else — phone resolution, PDF generation, service
type — is xlsx-native and 1C-free by construction.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.models.auto_notification_log import AutoNotificationLog
from app.models.notification import NotificationType
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.notification import NotificationSend
from app.services.auto_notification_service import astana_today, reserve_send_slot
from app.services.counterparty_cache_service import find_counterparty_in_cache
from app.services.invoice_access import normalize_counterparty_id
from app.services.nova_buh_1c_client import _pdf_payload_has_supplier_banks
from app.services.notification_service import NotificationService
from app.services.tenant_1c import get_tenant_by_id
from app.services.xlsx_invoice_pdf import (
    _counterparty_phone,
    build_xlsx_invoice_payload,
    render_xlsx_invoice_pdf,
)

logger = logging.getLogger(__name__)


def _notification_type_for_status(status) -> NotificationType:
    """Deliberately duplicated from bulk_debtor_notify_service.py's own
    _notification_type_for_status (same logic, same name) rather than
    extracted to a shared module — this module's whole reason to exist is
    to change nothing in bulk_debtor_notify_service.py before tomorrow's
    real send; even a pure no-behavior-change refactor of that file (remove
    the local def, import from a new shared spot instead) is still a diff
    to code the pure-1C path depends on today. Revisit post-launch."""
    raw = status.value if hasattr(status, "value") else str(status or "").lower()
    if raw == PaymentStatus.OVERDUE.value:
        return NotificationType.OVERDUE
    if raw == PaymentStatus.UNPAID.value:
        return NotificationType.THREE_DAYS
    return NotificationType.SAME_DAY


def _matching_payments_query(
    db: Session,
    *,
    tenant_id: int,
    period: str,
    service_type: Optional[str] = None,
    counterparty_id: Optional[str] = None,
    require_amount: bool = False,
):
    """Shared filter — used by count_xlsx_invoice_candidates,
    queue_xlsx_invoice_notifications and preview_xlsx_invoice_notifications
    so the three can never quietly disagree on which rows are in scope."""
    query = db.query(TenantPayment).filter(
        TenantPayment.tenant_id == tenant_id,
        TenantPayment.source == "xlsx",
        TenantPayment.period == period,
    )
    if require_amount:
        query = query.filter(TenantPayment.amount.isnot(None), TenantPayment.amount != 0)
    if service_type:
        query = query.filter(TenantPayment.service_type == service_type.strip().lower())
    if counterparty_id:
        cp_key = normalize_counterparty_id(counterparty_id)
        query = query.filter(func.lower(TenantPayment.counterparty_id) == cp_key)
    return query


def _slot_already_taken(
    db: Session, tenant_id: int, invoice_id: str, service_type: str, trigger: str
) -> bool:
    """Read-only twin of reserve_send_slot's uniqueness check — used by the
    dry-run preview so it can report "would be a duplicate" WITHOUT
    actually inserting the guard row. Calling the real reserve_send_slot
    during a preview would consume today's slot, and the real send
    afterward would then see it as already-sent and skip it — the exact
    opposite of what a preview promising "so it all works when I actually
    click send" needs to guarantee."""
    return (
        db.query(AutoNotificationLog)
        .filter(
            AutoNotificationLog.tenant_id == tenant_id,
            AutoNotificationLog.invoice_id == invoice_id,
            AutoNotificationLog.service_type == service_type,
            AutoNotificationLog.trigger_kind == trigger,
        )
        .first()
        is not None
    )


def count_xlsx_invoice_candidates(
    db: Session,
    *,
    tenant_id: int,
    period: str,
    service_type: Optional[str] = None,
    counterparty_id: Optional[str] = None,
) -> int:
    """Cheap (no rendering, no send) count for a fast endpoint response
    while the real pass runs in the background — same purpose as
    bulk_debtor_notify_service.count_debtor_candidates."""
    return _matching_payments_query(
        db,
        tenant_id=tenant_id,
        period=period,
        service_type=service_type,
        counterparty_id=counterparty_id,
        require_amount=True,
    ).count()


def preview_xlsx_invoice_notifications(
    db: Session,
    *,
    tenant_id: int,
    period: str,
    service_type: Optional[str] = None,
    counterparty_id: Optional[str] = None,
) -> dict:
    """Dry run: reports exactly what queue_xlsx_invoice_notifications WOULD
    do, with zero side effects — no AutoNotificationLog row is written (see
    _slot_already_taken), no Notification is created, no WhatsApp message
    is sent. Skips the PDF-rendering step entirely (build_xlsx_invoice_payload
    + a bank-fields check instead of the full generate_formal_invoice_document
    call) so this stays fast enough to answer synchronously even for ~150
    rows — no live 1C calls either way, this was never the slow part.

    Intended use: call this before queue_xlsx_invoice_notifications /
    POST /send-xlsx-invoices, fix what's fixable from the "skipped" list
    (missing phone -> enter it in admin; missing requisites -> fill the
    tenant's bank details), then send for real."""
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return {
            "would_queue": 0,
            "skipped_no_phone": 0,
            "skipped_no_amount": 0,
            "skipped_missing_requisites": 0,
            "skipped_duplicate": 0,
            "candidates": 0,
            "skipped_rows": [],
            "message": "Арендатор не найден",
        }

    payments = _matching_payments_query(
        db, tenant_id=tenant_id, period=period, service_type=service_type,
        counterparty_id=counterparty_id,
    ).order_by(TenantPayment.id).all()

    trigger = f"xlsx_bulk_{astana_today().isoformat()}"

    would_queue = 0
    skipped_no_phone = 0
    skipped_no_amount = 0
    skipped_missing_requisites = 0
    skipped_duplicate = 0
    skipped_rows: list[dict] = []

    def _row(payment: TenantPayment, reason: str) -> dict:
        return {
            "tenant_name": payment.tenant_name,
            "counterparty_id": payment.counterparty_id or "",
            "amount": float(payment.amount) if payment.amount is not None else None,
            "period": payment.period,
            "service_type": payment.service_type or "",
            "reason": reason,
        }

    for payment in payments:
        if not payment.amount:
            skipped_no_amount += 1
            skipped_rows.append(_row(payment, "no_amount"))
            continue

        cp_id = payment.counterparty_id or ""
        counterparty_cache = find_counterparty_in_cache(db, tenant_id, cp_id) if cp_id else None
        phone = _counterparty_phone(db, tenant, cp_id, counterparty_cache)
        if not phone:
            skipped_no_phone += 1
            skipped_rows.append(_row(payment, "no_phone"))
            continue

        st = payment.service_type or "xlsx"
        if _slot_already_taken(db, tenant_id, payment.invoice_id, st, trigger):
            skipped_duplicate += 1
            skipped_rows.append(_row(payment, "duplicate"))
            continue

        payload = build_xlsx_invoice_payload(db, payment, tenant)
        if not _pdf_payload_has_supplier_banks(payload):
            skipped_missing_requisites += 1
            skipped_rows.append(_row(payment, "missing_requisites"))
            continue

        would_queue += 1

    msg = (
        f"Ушло бы: {would_queue}. Без телефона: {skipped_no_phone}. "
        f"Без суммы: {skipped_no_amount}. Без реквизитов поставщика: {skipped_missing_requisites}. "
        f"Уже отправлено сегодня (повтор): {skipped_duplicate}."
    )

    return {
        "would_queue": would_queue,
        "skipped_no_phone": skipped_no_phone,
        "skipped_no_amount": skipped_no_amount,
        "skipped_missing_requisites": skipped_missing_requisites,
        "skipped_duplicate": skipped_duplicate,
        "candidates": len(payments),
        "skipped_rows": skipped_rows,
        "message": msg,
    }


def run_xlsx_invoice_notifications_background(
    *,
    tenant_id: int,
    period: str,
    service_type: Optional[str],
    counterparty_id: Optional[str],
    force: bool,
) -> None:
    """BackgroundTasks wrapper — own DB session, same reason as
    bulk_debtor_notify_service.run_debtor_notifications_background: the
    request-scoped session from the endpoint is already closed by the time
    FastAPI actually runs a background task. Even without any live 1C
    calls, ~150 renders+WhatsApp-API-calls in one request can still run
    long enough to trip a gateway timeout — same 504 this app has already
    hit for the 1C bulk path, same fix (endpoint answers immediately, real
    work happens after)."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        result = queue_xlsx_invoice_notifications(
            db,
            tenant_id=tenant_id,
            period=period,
            service_type=service_type,
            counterparty_id=counterparty_id,
            force=force,
        )
        logger.info("xlsx bulk notify (background) finished tenant=%s: %s", tenant_id, result)
    except Exception:
        logger.exception("xlsx bulk notify (background) failed tenant=%s", tenant_id)
    finally:
        db.close()


def queue_xlsx_invoice_notifications(
    db: Session,
    *,
    tenant_id: int,
    period: str,
    service_type: Optional[str] = None,
    counterparty_id: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Sends the WhatsApp invoice for every source="xlsx" TenantPayment row
    matching (tenant_id, period[, service_type][, counterparty_id]).

    Unlike bulk_debtor_notify_service.queue_debtor_notifications, this does
    NOT filter by payment status (unpaid/overdue) — the point here is
    distributing this month's invoices to everyone, not chasing debtors;
    a tenant who already paid still gets their invoice. Rows with
    amount in (None, 0) are skipped (nothing to invoice).

    force=True — same meaning as the 1C bulk endpoint's BulkDebtorNotifyRequest.force:
    releases an existing today's send-slot for a row before retrying, for
    when a first attempt is known to have failed to actually deliver.
    """
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return {
            "queued": 0,
            "skipped_no_phone": 0,
            "skipped_no_amount": 0,
            "skipped_missing_requisites": 0,
            "skipped_duplicate": 0,
            "errors": 1,
            "candidates": 0,
            "message": "Арендатор не найден",
        }

    payments = _matching_payments_query(
        db, tenant_id=tenant_id, period=period, service_type=service_type,
        counterparty_id=counterparty_id,
    ).order_by(TenantPayment.id).all()

    notification_service = NotificationService(db)
    trigger = f"xlsx_bulk_{astana_today().isoformat()}"

    queued = 0
    skipped_no_phone = 0
    skipped_no_amount = 0
    skipped_missing_requisites = 0
    skipped_duplicate = 0
    errors = 0

    for payment in payments:
        if not payment.amount:
            skipped_no_amount += 1
            continue

        cp_id = payment.counterparty_id or ""
        counterparty_cache = find_counterparty_in_cache(db, tenant_id, cp_id) if cp_id else None
        phone = _counterparty_phone(db, tenant, cp_id, counterparty_cache)
        if not phone:
            skipped_no_phone += 1
            continue

        st = payment.service_type or "xlsx"
        if not reserve_send_slot(
            db, tenant_id, cp_id, payment.invoice_id, st, trigger, phone, force=force
        ):
            skipped_duplicate += 1
            continue

        try:
            file_path = render_xlsx_invoice_pdf(db, payment, tenant)
        except MissingSupplierRequisitesError:
            skipped_missing_requisites += 1
            continue
        except Exception:
            errors += 1
            logger.exception(
                "xlsx bulk notify: render failed tenant_id=%s payment_id=%s",
                tenant_id,
                payment.id,
            )
            continue

        if not file_path:
            errors += 1
            logger.warning(
                "xlsx bulk notify: render returned no file tenant_id=%s payment_id=%s",
                tenant_id,
                payment.id,
            )
            continue

        try:
            data = NotificationSend(
                payment_id=payment.id,
                notification_type=_notification_type_for_status(payment.status),
                phone_number=phone,
                counterparty_id=cp_id,
                invoice_id=payment.invoice_id,
                service_type=st,
            )
            # defer_whatsapp=False — unlike the 1C bulk path, the PDF is
            # already rendered (fast, no live 1C round-trip involved at
            # all) — no need to defer PDF-fetching to the worker, just
            # hand it the finished file_path like the single-send xlsx
            # path already does.
            notification, _kafka_queued = notification_service.send_notification(
                data,
                file_path=file_path,
                tenant_id=tenant_id,
                counterparty_name=payment.tenant_name,
                immediate=False,
                defer_whatsapp=False,
            )
            queued += 1
        except Exception:
            errors += 1
            logger.exception(
                "xlsx bulk notify: send_notification failed tenant_id=%s payment_id=%s",
                tenant_id,
                payment.id,
            )
            try:
                db.rollback()
            except Exception:
                pass

    msg = (
        f"В очередь: {queued}. Без телефона: {skipped_no_phone}. "
        f"Без суммы: {skipped_no_amount}. Без реквизитов поставщика: {skipped_missing_requisites}. "
        f"Уже отправлено сегодня (повтор): {skipped_duplicate}. Ошибок: {errors}."
    )

    return {
        "queued": queued,
        "skipped_no_phone": skipped_no_phone,
        "skipped_no_amount": skipped_no_amount,
        "skipped_missing_requisites": skipped_missing_requisites,
        "skipped_duplicate": skipped_duplicate,
        "errors": errors,
        "candidates": len(payments),
        "message": msg,
    }
