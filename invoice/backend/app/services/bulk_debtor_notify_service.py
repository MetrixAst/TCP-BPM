"""Массовая рассылка WhatsApp должникам за выбранный период."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.catalog import CounterpartyPhone
from app.models.notification import NotificationType
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.notification import NotificationSend
from app.services.auto_notification_service import (
    _resolve_auto_notify_phone,
    astana_today,
    release_send_slot,
    reserve_send_slot,
)
from app.services.invoice_access import (
    get_trc_id_for_tenant,
    invoice_service_types_from_1c,
    normalize_counterparty_id,
)
from app.services.invoice_service_type import ServiceType, parse_stored_service_types
from app.services.notification_service import NotificationService
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id
from app.services.tenant_payment_types import filter_service_types
from app.services.xlsx_import.precedence import exclude_shadowed_one_c_rows

logger = logging.getLogger(__name__)


def _notification_type_for_status(status: Optional[str]) -> NotificationType:
    raw = (status or "").lower()
    if raw == PaymentStatus.OVERDUE.value or raw == "overdue":
        return NotificationType.OVERDUE
    if raw == PaymentStatus.UNPAID.value or raw == "unpaid":
        return NotificationType.THREE_DAYS
    return NotificationType.SAME_DAY


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _debtor_payments_query(
    db: Session,
    tenant,
    *,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    counterparty_id: Optional[str] = None,
):
    """Общий фильтр для реального прохода (queue_debtor_notifications) и для
    быстрого предварительного count() в эндпоинте — один код, чтобы не
    расходились условия."""
    query = db.query(TenantPayment).filter(
        # tenant_id (FK), не ip_name==legal_name — см. аудит от 2026-08-25.
        TenantPayment.tenant_id == tenant.id,
        TenantPayment.invoice_id.isnot(None),
        TenantPayment.invoice_id != "",
        TenantPayment.status.in_([PaymentStatus.UNPAID, PaymentStatus.OVERDUE]),
    )
    # prefer_xlsx: без этого — если 1С ещё числит должником то, что excel
    # уже показывает оплаченным (или наоборот), два раза шлём разным
    # людям/дублируем WhatsApp за один и тот же долг (см. precedence.py).
    query = exclude_shadowed_one_c_rows(db, query, tenant.id)
    if counterparty_id and counterparty_id.strip():
        query = query.filter(
            func.lower(TenantPayment.counterparty_id)
            == normalize_counterparty_id(counterparty_id)
        )
    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    if df and dt:
        query = query.filter(
            TenantPayment.invoice_date >= df,
            TenantPayment.invoice_date <= dt,
        )
    elif period:
        query = query.filter(TenantPayment.period == period)
    return query


def count_debtor_candidates(
    db: Session,
    *,
    tenant_id: int,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    counterparty_id: Optional[str] = None,
) -> int:
    """Дешёвая (без 1С) прикидка количества счетов-должников — только для
    быстрого ответа эндпоинта, пока реальный проход идёт в фоне."""
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return 0
    return _debtor_payments_query(
        db,
        tenant,
        period=period,
        date_from=date_from,
        date_to=date_to,
        counterparty_id=counterparty_id,
    ).count()


def run_debtor_notifications_background(
    *,
    tenant_id: int,
    period: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    ignore_balance_filter: bool,
    only_service_types: Optional[list[str]],
    force: bool,
    counterparty_id: Optional[str],
) -> None:
    """Обёртка над queue_debtor_notifications для BackgroundTasks — своя
    сессия БД: request-scoped db из эндпоинта уже закрыта к моменту, когда
    FastAPI реально выполняет background-задачу (после отправки ответа),
    так что переиспользовать её нельзя. См. app/api/notifications.py
    send_debtors_bulk — эндпоинт больше не ждёт этот проход, чтобы не
    вылетать по таймауту шлюза (504) на большом списке должников."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        result = queue_debtor_notifications(
            db,
            tenant_id=tenant_id,
            period=period,
            date_from=date_from,
            date_to=date_to,
            ignore_balance_filter=ignore_balance_filter,
            only_service_types=only_service_types,
            force=force,
            counterparty_id=counterparty_id,
        )
        logger.info(
            "Bulk debtor notify (background) finished tenant=%s: %s",
            tenant_id,
            result,
        )
    except Exception:
        logger.exception(
            "Bulk debtor notify (background) failed tenant=%s", tenant_id
        )
    finally:
        db.close()


def queue_debtor_notifications(
    db: Session,
    *,
    tenant_id: int,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ignore_balance_filter: bool = False,
    only_service_types: Optional[list[str]] = None,
    force: bool = False,
    counterparty_id: Optional[str] = None,
) -> dict:
    """
    Ставит в очередь WhatsApp всем должникам (unpaid/overdue) за период/диапазон.
    Тип услуги (rent/utilities/operations) — по строкам счёта и ключевым словам из админки.

    counterparty_id: сузить до одного контрагента — та же механика (все его
    неоплаченные счета за период, по всем найденным типам услуги, с той же
    защитой от дублей), просто с кнопки «Отправить все счета» на карточке
    контрагента, а не для всех должников арендатора.

    ignore_balance_filter: явный опт-ин оператора — не резать по net (долг−аванс)
    из баланса 1С. По умолчанию (False) выключенные по балансу (net<=1, т.е. 1С
    показывает аванс/переплату) пропускаются — см. isRealDebtorByBalance на фронте.
    С флагом True шлём всем со статусом unpaid/overdue за период, независимо от
    того, что говорит баланс 1С — на случай, если баланс 1С не отражает реальный
    долг по конкретному счёту (известный открытый вопрос по надёжности данных
    некоторых ТРЦ, см. память ip-moon-excel-workflow).

    only_service_types: опт-ин оператора — слать только по выбранным типам
    счёта (подмножество rent/utilities/operations). Пусто/None — как раньше,
    по всем типам, которые фактически найдены в строках счёта.

    force: явный опт-ин оператора — снять существующую резервацию за сегодня
    (bulk_<date>) перед повторной попыткой и переотправить, даже если что-то
    успешно ушло в очередь ранее сегодня. Обычный сбой ДО постановки в
    очередь (ошибка/недоступность 1С и т.п.) теперь освобождает свой слот
    автоматически (см. except-блок ниже) — force для этого больше не нужен,
    обычный повторный клик по "Отправить должникам" сегодня же доотправит
    то, что не дошло. force остаётся ручным аварийным выходом на случай,
    когда сообщение реально ушло в очередь, но точно не долетело до
    получателя (например, провайдер WhatsApp упал уже после постановки в
    очередь) и это достоверно известно оператору.
    """
    requested_types: Optional[set[str]] = None
    if only_service_types:
        requested_types = {
            s.strip().lower() for s in only_service_types if s and s.strip()
        } or None

    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return {
            "queued": 0,
            "skipped_no_phone": 0,
            "skipped_no_service": 0,
            "skipped_no_invoice": 0,
            "errors": 1,
            "message": "Арендатор не найден",
        }

    integration = get_integration_for_tenant(db, tenant_id)
    if not integration.client:
        # Не бросаем весь проход: несмотря на название, ничего в цикле ниже
        # больше не требует живой 1С безусловно — payment уже взят из БД
        # (ensure_payment_for_counterparty теперь сначала смотрит в БД, см.
        # payment_service.py), классификация типа услуги уже пробует
        # payment.service_type первым и мягко деградирует в skipped_no_service
        # без него, а телефон берётся из админки, если она настроена.
        # Раньше один флап/недоступность 1С РОВНО в момент старта фонового
        # прохода тихо обнулял всю рассылку должникам — при этом эндпоинт уже
        # успел ответить оператору "рассылка запущена, найдено N" (см.
        # send_debtors_bulk в app/api/notifications.py: count_debtor_candidates
        # 1С не трогает вообще), так что оператор не видел вообще никакой
        # ошибки, а ручная отправка того же счёта минутой позже уже работала,
        # потому что 1С к тому моменту отошла (incident 2026-09-03).
        logger.warning(
            "Bulk debtor notify tenant=%s: 1C unavailable (%s) — continuing "
            "with DB-known payments/admin phones only; invoices without a "
            "stored service_type will be skipped (skipped_no_service).",
            tenant_id,
            integration.unavailable_message(),
        )

    if not (_parse_iso_date(date_from) and _parse_iso_date(date_to)) and not period:
        return {
            "queued": 0,
            "skipped_no_phone": 0,
            "skipped_no_service": 0,
            "skipped_no_invoice": 0,
            "errors": 1,
            "message": "Укажите период или диапазон дат",
        }
    query = _debtor_payments_query(
        db,
        tenant,
        period=period,
        date_from=date_from,
        date_to=date_to,
        counterparty_id=counterparty_id,
    )

    payments = query.order_by(TenantPayment.invoice_date.desc(), TenantPayment.id.desc()).all()
    trc_id = get_trc_id_for_tenant(db, tenant_id)
    notification_service = NotificationService(db)

    # если есть снимок balance — не шлём тем, у кого net <= 0 (аванс/ноль)
    # нет снимка → как раньше, только по unpaid/overdue счетам
    balance_map: dict = {}
    use_balance_filter = False
    try:
        from app.services.counterparty_balance_service import (
            balances_map_for_tenant,
            is_real_debtor_net,
            tenant_has_balance_snapshot,
        )

        use_balance_filter = tenant_has_balance_snapshot(db, tenant_id) and not ignore_balance_filter
        if use_balance_filter:
            balance_map = balances_map_for_tenant(db, tenant_id)
    except Exception as bal_exc:
        logger.warning("Bulk notify: balance filter off (%s)", bal_exc)
        use_balance_filter = False

    phone_cache: dict[str, Optional[CounterpartyPhone]] = {}
    service_cache: dict[str, list[ServiceType]] = {}
    queued = 0
    skipped_no_phone = 0
    skipped_no_service = 0
    skipped_service_type_filtered = 0
    skipped_no_invoice = 0
    skipped_no_debt = 0
    skipped_duplicate = 0
    errors = 0
    seen: set[tuple[str, str]] = set()
    pending_jobs: list[dict] = []
    # Один "слот" на (арендатор, счёт, тип услуги) в день — та же таблица и тот
    # же механизм идемпотентности (уникальный констрейнт в БД), что у авто-рассылки,
    # только trigger_kind свой ("bulk_<дата>" вместо "before5_<due_date>" и т.п.),
    # чтобы не пересекаться с её резервациями и не путать источник в журнале.
    # Повторный клик/повторный запуск /send-debtors в тот же день на тот же счёт
    # больше не продублирует сообщение.
    bulk_trigger = f"bulk_{astana_today().isoformat()}"

    from app.services.whatsapp_jobs import process_whatsapp_job
    from app.core.config import settings
    from app.services.job_queue import enqueue_whatsapp_job

    for payment in payments:
        invoice_id = (payment.invoice_id or "").strip()
        cp_id = (payment.counterparty_id or "").strip()
        if not invoice_id:
            skipped_no_invoice += 1
            continue
        if not cp_id:
            skipped_no_invoice += 1
            continue

        if use_balance_filter:
            bal = balance_map.get(normalize_counterparty_id(cp_id)) or balance_map.get(
                cp_id.strip().lower()
            )
            # нет строки в balance — не режем (мало ли новый контрагент)
            if bal is not None and not is_real_debtor_net(bal.get("net")):
                skipped_no_debt += 1
                continue

        inv_key = invoice_id.lower()
        if inv_key not in service_cache:
            # Real incident 2026-09-02: this used to ALWAYS go live to 1С
            # here (invoice_service_types_from_1c), on every single one of
            # 230+ invoices in a bulk run, even though sync_from_1c already
            # computed and stored the exact same classification on
            # payment.service_type — that's why the manual per-row send
            # (type already known/shown in the UI, no live call needed)
            # worked fine while the bulk path hung/timed out repeatedly on
            # a slow Nova org (Maxi Mall). Trust the already-synced field
            # first; only pay for a live lookup when it's genuinely empty
            # (legacy row, not yet synced).
            stored_types = parse_stored_service_types(payment.service_type)
            if stored_types:
                service_cache[inv_key] = filter_service_types(stored_types, tenant)
            else:
                # Минимальный объект счёта для разбора строк 1С
                class _Inv:
                    id = invoice_id
                    items = []

                try:
                    service_cache[inv_key] = filter_service_types(
                        invoice_service_types_from_1c(
                            integration.client, _Inv(), tenant
                        ),
                        tenant,
                    )
                except Exception as exc:
                    logger.warning(
                        "Bulk notify: service types failed invoice=%s: %s",
                        invoice_id,
                        exc,
                    )
                    service_cache[inv_key] = []

        service_types = service_cache[inv_key]
        if not service_types:
            skipped_no_service += 1
            continue
        if requested_types:
            service_types = [s for s in service_types if s in requested_types]
            if not service_types:
                skipped_service_type_filtered += 1
                continue

        cp_key = normalize_counterparty_id(cp_id)
        if trc_id and cp_key not in phone_cache:
            phone_cache[cp_key] = (
                db.query(CounterpartyPhone)
                .filter(
                    CounterpartyPhone.trc_id == trc_id,
                    CounterpartyPhone.one_c_counterparty_id.ilike(cp_key),
                )
                .first()
            )
        phone_row = phone_cache.get(cp_key) if trc_id else None

        ntype = _notification_type_for_status(
            payment.status.value if hasattr(payment.status, "value") else str(payment.status)
        )

        for service_type in service_types:
            send_key = (inv_key, service_type)
            if send_key in seen:
                continue
            seen.add(send_key)

            phone = _resolve_auto_notify_phone(
                db,
                tenant_id=tenant_id,
                trc_id=trc_id,
                integration=integration,
                phone_row=phone_row,
                cp_id=cp_id,
                service_type=service_type,
            )
            if not phone:
                skipped_no_phone += 1
                continue

            if not reserve_send_slot(
                db, tenant_id, cp_id, invoice_id, service_type, bulk_trigger, phone,
                force=force,
            ):
                skipped_duplicate += 1
                continue

            try:
                # `payment` is already the exact TenantPayment row for this
                # (tenant, counterparty, invoice) — it's what the query at
                # the top of this function fetched cp_id/invoice_id from in
                # the first place, so there's nothing left to "ensure": no
                # need to round-trip through payment_service (which used to
                # require a live 1C client here even for a row we already
                # had — see the 1C-availability comment above).
                data = NotificationSend(
                    payment_id=payment.id,
                    notification_type=ntype,
                    phone_number=phone,
                    counterparty_id=cp_id,
                    invoice_id=invoice_id,
                    service_type=service_type,
                )
                # Только запись в БД; PDF+WhatsApp — через Kafka / фон с service_type
                notification, _kafka_queued = notification_service.send_notification(
                    data,
                    file_path=None,
                    tenant_id=tenant_id,
                    counterparty_name=payment.tenant_name,
                    immediate=False,
                    defer_whatsapp=True,
                )
                job_payload = {
                    "type": "whatsapp_send",
                    "notification_id": notification.id,
                    "tenant_id": tenant_id,
                    "payment_id": notification.payment_id,
                    "file_path": None,
                    "counterparty_name": payment.tenant_name,
                    "invoice_id": invoice_id,
                    "counterparty_id": cp_id,
                    "service_type": service_type,
                }
                if settings.KAFKA_ENABLED and enqueue_whatsapp_job(job_payload):
                    queued += 1
                else:
                    pending_jobs.append(job_payload)
                    queued += 1
            except Exception as exc:
                errors += 1
                logger.exception(
                    "Bulk notify queue failed invoice=%s service=%s: %s",
                    invoice_id,
                    service_type,
                    exc,
                )
                try:
                    db.rollback()
                except Exception:
                    pass
                # Nothing was actually queued/sent for this row (the
                # exception happened before the job was handed off to
                # Kafka/the background thread) — release the "sent today"
                # slot reserve_send_slot just committed above, otherwise a
                # bulk_<date> reservation with no real send behind it
                # permanently blocks this invoice for the rest of the day
                # (bulk never reused release_send_slot for this — see its
                # docstring — on the assumption failures here meant a real
                # delivery attempt happened; they don't). Without this, a
                # transient failure here forced operators to know about and
                # use force=True just to retry the same day.
                try:
                    release_send_slot(
                        db, tenant_id, invoice_id, service_type, bulk_trigger
                    )
                except Exception:
                    logger.exception(
                        "Bulk notify: failed to release send slot invoice=%s service=%s",
                        invoice_id,
                        service_type,
                    )

    if hasattr(integration, "close"):
        try:
            integration.close()
        except Exception:
            pass

    # Без Kafka: PDF+WhatsApp в фоне после ответа API
    if pending_jobs:
        import threading

        jobs = list(pending_jobs)

        def _run_jobs() -> None:
            for job in jobs:
                try:
                    process_whatsapp_job(job)
                except Exception:
                    logger.exception(
                        "Bulk notify background job failed notification_id=%s",
                        job.get("notification_id"),
                    )

        threading.Thread(
            target=_run_jobs,
            daemon=True,
            name=f"bulk-debtor-notify-{tenant_id}",
        ).start()

    msg = (
        f"В очередь: {queued}. Без телефона: {skipped_no_phone}. "
        f"Без типа услуги: {skipped_no_service}. Ошибок: {errors}."
    )
    if requested_types and skipped_service_type_filtered:
        msg += f" Не подходит под выбранный тип счёта: {skipped_service_type_filtered}."
    if use_balance_filter and skipped_no_debt:
        msg += f" Пропущено (аванс/нет долга по балансу): {skipped_no_debt}."
    if skipped_duplicate:
        msg += f" Уже отправлено сегодня (повтор): {skipped_duplicate}."

    return {
        "queued": queued,
        "skipped_no_phone": skipped_no_phone,
        "skipped_no_service": skipped_no_service,
        "skipped_service_type_filtered": skipped_service_type_filtered,
        "skipped_no_invoice": skipped_no_invoice,
        "skipped_no_debt": skipped_no_debt,
        "skipped_duplicate": skipped_duplicate,
        "debtor_invoices": len(payments),
        "errors": errors,
        "message": msg,
    }
