"""Авто-рассылка неоплаченных счетов (OData и COM).

Проверка каждый час: новые счета, контрагенты, статус оплаты из 1С (+ sync в БД).
Оплаченные счета пропускаем. Неоплаченные — WhatsApp строго в 6 фиксированных
моментов на счёт (не ежедневно):
  - за 5 и за 3 дня до срока оплаты;
  - в день срока оплаты;
  - через 1, 3 и 5 дней после срока (если всё ещё не оплачен).

Каждый момент отправляется максимум один раз за всё время жизни счёта
(журнал auto_notification_logs, ключ — счёт+тип платежа+момент). Отправка
только в окне 09:00–18:00 по Астане (Asia/Almaty).

Арендатор может поставить контрагента на паузу (CounterpartyPhone.auto_notify_paused,
кнопка в invoice-client) — тогда авто-рассылка пропускает его целиком, все
service_type и счета. Ручную отправку и массовую /send-debtors не затрагивает.

Либо арендатор может отключить авто-рассылку для СЕБЯ целиком (Tenant.auto_notify_paused,
кнопка «Отключить авто-напоминания для всех») — run_for_tenant тогда возвращает
0 сразу, до обращения к 1С, независимо от точечных пауз по контрагентам.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auto_notification_log import AutoNotificationLog
from app.models.catalog import CounterpartyPhone, Tenant
from app.models.notification import NotificationType
from app.schemas.notification import NotificationSend
from app.services.counterparty_phone_routing import resolve_phone_for_service
from app.services.payment_status_rules import paid_enough
from app.services.invoice_access import (
    collect_allowed_phones,
    get_trc_id_for_tenant,
    invoice_service_types_from_1c,
    normalize_counterparty_id,
)
from app.services.invoice_service_type import (
    ServiceType,
    due_date_in_invoice_month,
    due_day_for_service_type,
    tenant_due_day_for_service,
)
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id, tenant_has_1c_credentials
from app.services.tenant_payment_types import filter_service_types

logger = logging.getLogger(__name__)

ASTANA_TZ = ZoneInfo("Asia/Almaty")
SEND_WINDOW_START_HOUR = 9
SEND_WINDOW_END_HOUR = 18

# Смещения от due_date (в днях): отрицательные — заранее, положительные —
# после просрочки. 0 — сам день срока (NotificationType.SAME_DAY).
_REMINDER_OFFSETS_TO_TYPE = {
    -5: NotificationType.WEEK_BEFORE,
    -3: NotificationType.THREE_DAYS,
    0: NotificationType.SAME_DAY,
    1: NotificationType.OVERDUE,
    3: NotificationType.OVERDUE,
    5: NotificationType.OVERDUE,
}


def _warn_if_whatsapp_instance_not_authorized(tenant: Tenant) -> None:
    """Раз в час на арендатора — не в горячем пути отправки одного сообщения.
    logger.error попадает в Sentry (см. app/main.py sentry_sdk.init), поэтому
    "номер отвалился/забанен" не потеряется среди обычных failed-отправок."""
    try:
        from app.services.whatsapp_service import WhatsAppService

        whatsapp = WhatsAppService.for_tenant(tenant)
        state = whatsapp.get_state_instance()
        if state and state != "authorized":
            logger.error(
                "Green API instance NOT authorized: tenant=%s state=%s instance=%s — "
                "WhatsApp-отправки этому арендатору не дойдут, пока не восстановится",
                tenant.id,
                state,
                whatsapp.id_instance,
            )
    except Exception as exc:
        logger.warning("Auto notify: instance state check failed tenant=%s: %s", tenant.id, exc)


def astana_now() -> datetime:
    return datetime.now(ASTANA_TZ)


def astana_today() -> date:
    return astana_now().date()


def in_sending_window(now: Optional[datetime] = None) -> bool:
    now = now or astana_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=ASTANA_TZ)
    else:
        now = now.astimezone(ASTANA_TZ)
    return SEND_WINDOW_START_HOUR <= now.hour <= SEND_WINDOW_END_HOUR


def _parse_invoice_date(raw: str) -> Optional[date]:
    if not raw:
        return None
    text = str(raw).strip().split("T")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _resolve_auto_notify_phone(
    db: Session,
    *,
    tenant_id: int,
    trc_id: Optional[int],
    integration,
    phone_row: Optional[CounterpartyPhone],
    cp_id: str,
    service_type: ServiceType,
) -> Optional[str]:
    """Телефон: сначала админка, иначе из 1С (как при ручной отправке)."""
    phone = resolve_phone_for_service(phone_row, service_type)
    if phone:
        return phone
    allowed = collect_allowed_phones(db, tenant_id, cp_id, integration)
    if not allowed:
        return None
    return resolve_phone_for_service(
        phone_row,
        service_type,
        fallback_phones=sorted(allowed),
    )


def _due_day_for_tenant(tenant: Tenant, service_type: str) -> int:
    return tenant_due_day_for_service(tenant, service_type)


def _due_date_for_invoice(
    inv_date: date,
    rent_due_day: int,
    utilities_due_day: int,
    operations_due_day: int,
    service_type: str,
) -> date:
    due_day = due_day_for_service_type(
        service_type,
        rent=rent_due_day,
        utilities=utilities_due_day,
        operations=operations_due_day,
    )
    return due_date_in_invoice_month(inv_date, due_day)


def _is_unpaid(invoice) -> bool:
    status = str(getattr(invoice, "payment_status", "") or "").lower()
    if status == "paid":
        return False
    paid_amount = float(getattr(invoice, "paid_amount", 0) or 0)
    amount = float(getattr(invoice, "amount", 0) or 0)
    if amount > 0 and paid_enough(amount, paid_amount):
        return False
    return True


def _offset_to_due_date(today: date, due_date: date) -> int:
    """<0 — дней до срока, >0 — дней просрочки, 0 — сам день срока."""
    return (today - due_date).days


def _trigger_kind_for_offset(offset: int, due_date: date) -> str:
    if offset == 0:
        return f"dueday_{due_date.isoformat()}"
    sign = "before" if offset < 0 else "after"
    return f"{sign}{abs(offset)}_{due_date.isoformat()}"


def _notification_type_for_offset(offset: int) -> NotificationType:
    return _REMINDER_OFFSETS_TO_TYPE.get(offset, NotificationType.OVERDUE)


def _invoice_fetch_since(today: date) -> datetime:
    """С начала прошлого месяца — чтобы догонять просрочку на границе месяцев."""
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    return datetime(year, month, 1)


def _payment_lookup_window(since: datetime, today: date) -> tuple[str, str]:
    """Окно входящих платежей 1С: с даты выборки счетов + запас после срока."""
    since_day = since.strftime("%Y-%m-%d")
    until_day = today.isoformat()
    try:
        from app.services.odata_1c_client import OData1CClient

        until_day = OData1CClient._payment_until_with_grace(until_day) or until_day
    except Exception:
        pass
    return since_day, until_day


def _invoice_in_billing_period(invoice, period: str, client) -> bool:
    belongs = getattr(client, "_invoice_belongs_to_period", None)
    if not belongs or not period:
        return True
    due_raw = getattr(invoice, "due_date", None)
    if due_raw is not None and hasattr(due_raw, "isoformat"):
        due_raw = due_raw.isoformat()
    return bool(belongs(getattr(invoice, "date", None), due_raw, period))


def _pick_triggers_for_run(
    invoice,
    today: date,
    rent_due_day: int,
    utilities_due_day: int,
    operations_due_day: int,
    service_type: str,
    *,
    already_sent,
) -> List[str]:
    """
    Ровно 6 моментов за весь срок жизни счёта, не ежедневно:
    за 5/3 дня до due_date, в день due_date, и через 1/3/5 дней после
    (если не оплачен).
    """
    inv_date = _parse_invoice_date(getattr(invoice, "date", "") or "")
    if not inv_date or today < inv_date:
        return []

    due_date = _due_date_for_invoice(
        inv_date, rent_due_day, utilities_due_day, operations_due_day, service_type
    )

    offset = _offset_to_due_date(today, due_date)
    if offset not in _REMINDER_OFFSETS_TO_TYPE:
        return []

    trigger = _trigger_kind_for_offset(offset, due_date)
    if already_sent(trigger):
        return []
    return [trigger]


def _paused_counterparty_ids(db: Session, trc_id: int) -> set:
    """Контрагенты, для которых арендатор поставил авто-рассылку на паузу
    (кнопка в invoice-client) — CounterpartyPhone.auto_notify_paused."""
    rows = (
        db.query(CounterpartyPhone.one_c_counterparty_id)
        .filter(
            CounterpartyPhone.trc_id == trc_id,
            CounterpartyPhone.auto_notify_paused.is_(True),
        )
        .all()
    )
    return {normalize_counterparty_id(row[0]) for row in rows if row[0]}


def is_already_sent(
    db: Session,
    tenant_id: int,
    invoice_id: str,
    service_type: str,
    trigger: str,
) -> bool:
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


def reserve_send_slot(
    db: Session,
    tenant_id: int,
    counterparty_id: str,
    invoice_id: str,
    service_type: str,
    trigger: str,
    phone: str,
    force: bool = False,
) -> bool:
    """Бронь до отправки в auto_notification_logs — общий механизм идемпотентности
    и для авто-рассылки (trigger = смещение+due_date), и для массовой рассылки
    должникам (trigger = "bulk_<дата>", см. bulk_debtor_notify_service.py) —
    повторный запуск с тем же ключом не продублирует сообщение.

    force=True — ручной аварийный опт-ин (см. BulkDebtorNotifyRequest.force):
    снимает существующую резервацию по этому ключу перед новой попыткой,
    когда известно, что предыдущая отправка не дошла (например, WhatsApp-
    провайдер был недоступен) и ждать следующего дня недопустимо."""
    if force:
        release_send_slot(db, tenant_id, invoice_id, service_type, trigger)
    try:
        db.add(
            AutoNotificationLog(
                tenant_id=tenant_id,
                counterparty_id=normalize_counterparty_id(counterparty_id),
                invoice_id=invoice_id,
                service_type=service_type,
                trigger_kind=trigger,
                phone_number=phone,
            )
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def release_send_slot(
    db: Session,
    tenant_id: int,
    invoice_id: str,
    service_type: str,
    trigger: str,
) -> None:
    """Снять бронь, если отправка не удалась — повторим на следующей проверке.
    Авто-рассылка использует это на каждой почасовой попытке. Массовая
    рассылка должникам (bulk_<дата>) тоже вызывает это, но только когда сам
    проход по строке упал ДО реальной отправки (ошибка в очереди/подготовке —
    см. except-блок в queue_debtor_notifications): раньше не освобождала
    никогда, из-за чего один сбой навсегда «сжигал» слот на сегодня и
    ретрай без force=True молча ничего не отправлял (incident 2026-09-03).
    Не вызывается, если сообщение уже реально ушло в Kafka/очередь — тогда
    бронь должна остаться, иначе повторный запуск продублирует отправку."""
    row = (
        db.query(AutoNotificationLog)
        .filter(
            AutoNotificationLog.tenant_id == tenant_id,
            AutoNotificationLog.invoice_id == invoice_id,
            AutoNotificationLog.service_type == service_type,
            AutoNotificationLog.trigger_kind == trigger,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()


class AutoNotificationService:
    def __init__(self, db: Session):
        self.db = db

    def _refresh_tenant_data_for_check(self, tenant_id: int, period: str) -> None:
        """Платежи и контрагенты из 1С в PostgreSQL перед live-проверкой."""
        try:
            from app.services.payment_sync_jobs import run_payment_sync

            run_payment_sync(tenant_id, period)
        except Exception as exc:
            logger.warning(
                "Auto notify: payment sync failed tenant=%s period=%s: %s",
                tenant_id,
                period,
                exc,
            )
        try:
            from app.services.counterparty_cache_service import run_counterparty_cache_sync

            run_counterparty_cache_sync(tenant_id)
        except Exception as exc:
            logger.warning(
                "Auto notify: counterparty sync failed tenant=%s: %s",
                tenant_id,
                exc,
            )

    def run_for_all_tenants(self) -> int:
        tenants = (
            self.db.query(Tenant)
            .filter(Tenant.is_active.is_(True))
            .filter(Tenant.green_api_id_instance.isnot(None))
            .filter(Tenant.green_api_api_token.isnot(None))
            .all()
        )
        sent_total = 0
        can_send = in_sending_window()
        if not can_send:
            logger.info(
                "Auto notify check (no send): outside Astana window %s:00–%s:00",
                SEND_WINDOW_START_HOUR,
                SEND_WINDOW_END_HOUR,
            )
        for tenant in tenants:
            if not tenant_has_1c_credentials(tenant):
                continue
            try:
                sent_total += self.run_for_tenant(tenant.id, can_send=can_send)
            except Exception as exc:
                logger.exception("Auto notify failed for tenant %s: %s", tenant.id, exc)
        return sent_total

    def run_for_tenant(self, tenant_id: int, *, can_send: Optional[bool] = None) -> int:
        tenant = get_tenant_by_id(self.db, tenant_id)
        if not tenant:
            return 0
        if getattr(tenant, "auto_notify_paused", False):
            logger.info(
                "Auto notify check tenant=%s: paused for everyone (tenant.auto_notify_paused)",
                tenant_id,
            )
            return 0
        integration = get_integration_for_tenant(self.db, tenant_id)
        if not integration.client:
            logger.warning("Auto notify: 1C unavailable for tenant %s", tenant_id)
            return 0

        if can_send is None:
            can_send = in_sending_window()

        if can_send:
            _warn_if_whatsapp_instance_not_authorized(tenant)

        today = astana_today()
        rent_due = _due_day_for_tenant(tenant, "rent")
        util_due = _due_day_for_tenant(tenant, "utilities")
        ops_due = _due_day_for_tenant(tenant, "operations")
        period = f"{today.year}-{today.month:02d}"
        since = _invoice_fetch_since(today)
        payment_since, payment_until = _payment_lookup_window(since, today)
        trc_id = get_trc_id_for_tenant(self.db, tenant_id)
        paused_cp_ids = _paused_counterparty_ids(self.db, trc_id) if trc_id else set()

        self._refresh_tenant_data_for_check(tenant_id, period)

        sent_count = 0
        unpaid_count = 0
        paid_skipped = 0
        period_skipped = 0
        paused_skipped = 0
        seen_targets: set[tuple[str, str]] = set()
        service_types_cache: dict[str, List[ServiceType]] = {}
        try:
            client = integration.client
            invoices = client.get_invoices(
                since=since,
                limit=50000,
                due_day=rent_due,
                enrich_payment_status=True,
                payment_since=payment_since,
                payment_until=payment_until,
                utilities_due_day=util_due,
                operations_due_day=ops_due,
                period=period,
            )

            phone_cache: dict[str, Optional[CounterpartyPhone]] = {}

            for invoice in invoices:
                if not _invoice_in_billing_period(invoice, period, client):
                    period_skipped += 1
                    continue

                if not _is_unpaid(invoice):
                    paid_skipped += 1
                    continue

                unpaid_count += 1
                if not can_send:
                    continue

                cp_id = (invoice.counterparty_id or "").strip()
                if not cp_id:
                    continue

                if paused_cp_ids and normalize_counterparty_id(cp_id) in paused_cp_ids:
                    paused_skipped += 1
                    continue

                invoice_id = (invoice.id or "").strip()
                if not invoice_id:
                    continue

                invoice_key = invoice_id.lower()
                if invoice_key not in service_types_cache:
                    service_types_cache[invoice_key] = invoice_service_types_from_1c(
                        integration.client, invoice, tenant
                    )
                service_types = filter_service_types(
                    service_types_cache[invoice_key], tenant
                )
                if not service_types:
                    logger.warning(
                        "Auto notify skip: no service type tenant=%s invoice=%s",
                        tenant_id,
                        invoice_id,
                    )
                    continue

                if trc_id and cp_id not in phone_cache:
                    phone_cache[cp_id] = (
                        self.db.query(CounterpartyPhone)
                        .filter(
                            CounterpartyPhone.trc_id == trc_id,
                            CounterpartyPhone.one_c_counterparty_id.ilike(cp_id),
                        )
                        .first()
                    )
                phone_row = phone_cache.get(cp_id) if trc_id else None

                for service_type in service_types:
                    phone = _resolve_auto_notify_phone(
                        self.db,
                        tenant_id=tenant_id,
                        trc_id=trc_id,
                        integration=integration,
                        phone_row=phone_row,
                        cp_id=cp_id,
                        service_type=service_type,
                    )
                    if not phone:
                        logger.warning(
                            "Auto notify skip: no phone tenant=%s cp=%s invoice=%s service=%s",
                            tenant_id,
                            cp_id,
                            invoice_id,
                            service_type,
                        )
                        continue

                    triggers = _pick_triggers_for_run(
                        invoice,
                        today,
                        rent_due,
                        util_due,
                        ops_due,
                        service_type,
                        already_sent=lambda t: is_already_sent(
                            self.db, tenant_id, invoice_id, service_type, t
                        ),
                    )
                    for trigger in triggers:
                        send_key = (invoice_id, service_type, trigger)
                        if send_key in seen_targets:
                            continue
                        seen_targets.add(send_key)

                        if not reserve_send_slot(
                            self.db, tenant_id, cp_id, invoice_id, service_type, trigger, phone
                        ):
                            continue

                        inv_date = _parse_invoice_date(getattr(invoice, "date", "") or "")
                        due_date = (
                            _due_date_for_invoice(
                                inv_date, rent_due, util_due, ops_due, service_type
                            )
                            if inv_date
                            else today
                        )
                        ntype = _notification_type_for_offset(_offset_to_due_date(today, due_date))

                        ok = self._send_one(
                            tenant_id=tenant_id,
                            tenant=tenant,
                            integration=integration,
                            counterparty_id=cp_id,
                            counterparty_name=invoice.counterparty_name or "",
                            invoice_id=invoice_id,
                            phone=phone,
                            service_type=service_type,
                            trigger=trigger,
                            notification_type=ntype,
                            period=period,
                            rent_due=rent_due,
                            util_due=util_due,
                            ops_due=ops_due,
                            known_invoice=invoice,
                        )
                        if ok:
                            sent_count += 1
                            logger.info(
                                "Auto notify ok: cp=%s invoice=%s (%s) trigger=%s phone=%s",
                                cp_id,
                                invoice_id,
                                service_type,
                                trigger,
                                phone,
                            )
                        else:
                            release_send_slot(
                                self.db, tenant_id, invoice_id, service_type, trigger
                            )

            logger.info(
                "Auto notify check tenant=%s invoices=%s unpaid=%s paid_skip=%s "
                "period_skip=%s paused_skip=%s sent=%s can_send=%s payment_window=%s..%s",
                tenant_id,
                len(invoices),
                unpaid_count,
                paid_skipped,
                period_skipped,
                paused_skipped,
                sent_count,
                can_send,
                payment_since,
                payment_until,
            )
        finally:
            if hasattr(integration, "close"):
                try:
                    integration.close()
                except Exception:
                    pass
        return sent_count

    def _invoice_still_unpaid(
        self,
        integration,
        *,
        invoice_id: str,
        period: Optional[str] = None,
        rent_due: int,
        util_due: int,
        ops_due: int,
        known_invoice=None,
    ) -> bool:
        """Live-проверка одного счёта в 1С непосредственно перед WhatsApp."""
        client = integration.client
        if not client:
            return False
        fetch = getattr(client, "fetch_invoice_payment_status", None)
        if not callable(fetch):
            logger.warning(
                "Auto notify: client has no fetch_invoice_payment_status invoice=%s",
                invoice_id,
            )
            return False
        today = astana_today()
        period = period or f"{today.year}-{today.month:02d}"
        since = _invoice_fetch_since(today)
        payment_since, payment_until = _payment_lookup_window(since, today)
        try:
            invoice = fetch(
                invoice_id,
                due_day=rent_due,
                payment_since=payment_since,
                payment_until=payment_until,
                utilities_due_day=util_due,
                operations_due_day=ops_due,
                period=period,
            )
        except Exception as exc:
            logger.warning(
                "Auto notify: live invoice check failed invoice=%s: %s", invoice_id, exc
            )
            invoice = None
        if invoice is None:
            if known_invoice is not None and _is_unpaid(known_invoice):
                logger.info(
                    "Auto notify: using list invoice (live check empty) invoice=%s status=%s",
                    invoice_id,
                    getattr(known_invoice, "payment_status", ""),
                )
                return True
            logger.warning(
                "Auto notify: invoice not found in 1C tenant check invoice=%s",
                invoice_id,
            )
            return False
        if not _is_unpaid(invoice):
            logger.info(
                "Auto notify skip: invoice paid in 1C invoice=%s status=%s paid=%s amount=%s",
                invoice_id,
                getattr(invoice, "payment_status", ""),
                getattr(invoice, "paid_amount", ""),
                getattr(invoice, "amount", ""),
            )
            return False
        return True

    def _send_one(
        self,
        *,
        tenant_id: int,
        tenant: Tenant,
        integration,
        counterparty_id: str,
        counterparty_name: str,
        invoice_id: str,
        phone: str,
        service_type: str,
        trigger: str,
        notification_type: NotificationType,
        period: str,
        rent_due: int,
        util_due: int,
        ops_due: int,
        known_invoice=None,
    ) -> bool:
        payment_service = PaymentService(self.db, tenant_id=tenant_id)
        notification_service = NotificationService(self.db)
        try:
            if not self._invoice_still_unpaid(
                integration,
                invoice_id=invoice_id,
                period=period,
                rent_due=rent_due,
                util_due=util_due,
                ops_due=ops_due,
                known_invoice=known_invoice,
            ):
                return False

            payment = payment_service.ensure_payment_for_counterparty(
                counterparty_id,
                invoice_id,
                integration=integration,
            )
            file_path = integration.get_invoice_and_download(invoice_id, tenant=tenant)
            if not file_path:
                logger.warning(
                    "Auto notify: no PDF tenant=%s invoice=%s", tenant_id, invoice_id
                )
                return False

            data = NotificationSend(
                payment_id=payment.id,
                notification_type=notification_type,
                phone_number=phone,
                counterparty_id=counterparty_id,
                invoice_id=invoice_id,
            )
            notification_service.send_notification(
                data,
                file_path=file_path,
                tenant_id=tenant_id,
                counterparty_name=counterparty_name,
                immediate=False,
            )
            logger.info(
                "Auto notify sent tenant=%s invoice=%s service=%s trigger=%s type=%s phone=%s",
                tenant_id,
                invoice_id,
                service_type,
                trigger,
                notification_type.value,
                phone,
            )
            return True
        except Exception as exc:
            logger.exception(
                "Auto notify send failed tenant=%s invoice=%s: %s",
                tenant_id,
                invoice_id,
                exc,
            )
            self.db.rollback()
            return False
