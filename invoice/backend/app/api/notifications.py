from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile, File, Form, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
import base64
import logging
import tempfile
import os
from pathlib import Path
from app.models.notification import NotificationStatus, NotificationType

from app.api.deps import get_current_admin, security_scheme
from app.api.tenant_scope import resolve_tenant_id, scoped_tenant_id
from app.core.config import settings
from app.db.database import get_db
from app.models.catalog import AdminUser
from app.schemas.notification import (
    BulkDebtorNotifyRequest,
    BulkDebtorNotifyResponse,
    InvoiceEmailSendRequest,
    InvoiceEmailSendResponse,
    MessagePreviewResponse,
    NotificationResponse,
    NotificationCreate,
    NotificationSend,
    QuickMessageSendRequest,
    QuickMessageSendResponse,
    XlsxBulkNotifyPreviewResponse,
    XlsxBulkNotifyRequest,
    XlsxBulkNotifyResponse,
)
from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.services.invoice_access import (
    assert_phone_allowed_for_counterparty,
    find_cached_invoice_pdf,
    find_invoice_id_for_service_type,
    find_latest_invoice_id,
    normalize_counterparty_id,
    resolve_invoice_for_counterparty,
)
from app.services.tenant_payment_types import tenant_payment_types_enabled
from app.services.xlsx_invoice_pdf import find_latest_xlsx_payment, render_xlsx_invoice_pdf
from app.services.message_builder import build_whatsapp_message, service_type_label
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService
from app.services.bulk_debtor_notify_service import (
    count_debtor_candidates,
    run_debtor_notifications_background,
)
from app.services.xlsx_bulk_notify_service import (
    count_xlsx_invoice_candidates,
    preview_xlsx_invoice_notifications,
    run_xlsx_invoice_notifications_background,
)
from app.services.smtp_mail import send_smtp_email_with_attachment
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id, tenant_uses_nova_org
from app.services.whatsapp_service import WhatsAppService
from sqlalchemy import func

logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/send-debtors", response_model=BulkDebtorNotifyResponse)
def send_debtors_bulk(
    data: BulkDebtorNotifyRequest,
    background_tasks: BackgroundTasks,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """
    Разослать WhatsApp всем должникам за период/диапазон дат.
    Тип услуги в тексте — по строкам счёта и ключевым словам из админки.

    Сам проход по должникам (поход в 1С за типом услуги/привязкой платежа на
    каждый счёт) уходит в фон — на большом списке (сотни должников) это легко
    занимает больше времени, чем таймаут шлюза перед бэкендом, и раньше
    оператор получал 504, хотя рассылка на сервере продолжала идти и
    отправляла сообщения после того, как ответ клиенту уже потерялся.
    Эндпоинт теперь только: валидирует вход, быстро (без 1С) считает
    кандидатов и запускает реальную обработку в фоне — результат смотрите в
    журнале WhatsApp через несколько минут, а не в этом ответе.
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора (tenant)")
    if not data.period and not (data.date_from and data.date_to):
        raise HTTPException(
            status_code=400,
            detail="Укажите период (YYYY-MM) или диапазон дат date_from/date_to",
        )
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=400, detail="Арендатор не найден")

    candidates = count_debtor_candidates(
        db,
        tenant_id=tenant_id,
        period=data.period,
        date_from=data.date_from,
        date_to=data.date_to,
        counterparty_id=data.counterparty_id,
    )
    if candidates == 0:
        return BulkDebtorNotifyResponse(
            queued=0,
            debtor_invoices=0,
            message="Не найдено счетов-должников за указанный период",
        )

    background_tasks.add_task(
        run_debtor_notifications_background,
        tenant_id=tenant_id,
        period=data.period,
        date_from=data.date_from,
        date_to=data.date_to,
        ignore_balance_filter=data.ignore_balance_filter,
        only_service_types=data.service_types,
        force=data.force,
        counterparty_id=data.counterparty_id,
    )
    return BulkDebtorNotifyResponse(
        queued=0,
        debtor_invoices=candidates,
        message=(
            f"Рассылка запущена в фоне: найдено {candidates} счетов-должников. "
            "Отправка идёт по одному счёту через 1С — результат смотрите в "
            "журнале WhatsApp через несколько минут."
        ),
    )


@router.get("/send-xlsx-invoices/preview", response_model=XlsxBulkNotifyPreviewResponse)
def preview_xlsx_invoices_bulk(
    period: str = Query(..., description="YYYY-MM"),
    service_type: Optional[str] = Query(None),
    counterparty_id: Optional[str] = Query(None),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Dry run for POST /send-xlsx-invoices — same filters, zero side
    effects (see xlsx_bulk_notify_service.preview_xlsx_invoice_notifications
    docstring: no AutoNotificationLog row written, no message sent). Call
    this first, fix what's in skipped_rows (no_phone -> add it in admin,
    missing_requisites -> fill the tenant's bank details), then call the
    real endpoint — it will see the exact same candidates, nothing here
    consumes a send-slot. Synchronous (skips PDF rendering entirely, only
    checks whether the requisites needed for it are present) — fast enough
    for ~150 rows without needing to background it like the real send."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора (tenant)")
    if not get_tenant_by_id(db, tenant_id):
        raise HTTPException(status_code=400, detail="Арендатор не найден")

    result = preview_xlsx_invoice_notifications(
        db,
        tenant_id=tenant_id,
        period=period,
        service_type=service_type,
        counterparty_id=counterparty_id,
    )
    return XlsxBulkNotifyPreviewResponse(**result)


@router.post("/send-xlsx-invoices", response_model=XlsxBulkNotifyResponse)
def send_xlsx_invoices_bulk(
    data: XlsxBulkNotifyRequest,
    background_tasks: BackgroundTasks,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Разослать WhatsApp-счета, загруженные из Excel (TenantPayment
    source="xlsx"), за указанный период — отдельно от /send-debtors, чтобы
    не задевать 1С-путь ради этого (см. app/services/xlsx_bulk_notify_service.py
    docstring). Никогда не ходит в живую 1С — суммы и период из файла,
    контрагент/телефон из уже засинканного локально кэша.

    Как и /send-debtors, сам проход уходит в фон и не ждётся этим ответом —
    на ~150 арендаторах рендер+отправка каждого счёта всё равно суммарно
    может занять дольше таймаута шлюза перед бэкендом, даже без единого
    похода в 1С."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора (tenant)")
    if not get_tenant_by_id(db, tenant_id):
        raise HTTPException(status_code=400, detail="Арендатор не найден")

    candidates = count_xlsx_invoice_candidates(
        db,
        tenant_id=tenant_id,
        period=data.period,
        service_type=data.service_type,
        counterparty_id=data.counterparty_id,
    )
    if candidates == 0:
        return XlsxBulkNotifyResponse(
            queued=0,
            candidates=0,
            message="Не найдено загруженных из Excel счетов с суммой за указанный период",
        )

    background_tasks.add_task(
        run_xlsx_invoice_notifications_background,
        tenant_id=tenant_id,
        period=data.period,
        service_type=data.service_type,
        counterparty_id=data.counterparty_id,
        force=data.force,
    )
    return XlsxBulkNotifyResponse(
        queued=0,
        candidates=candidates,
        message=(
            f"Рассылка запущена в фоне: найдено {candidates} счетов из Excel. "
            "Результат смотрите в журнале WhatsApp через несколько минут."
        ),
    )


def _counterparty_email_from_cache(db: Session, tenant_id: int, counterparty_id: str) -> str:
    from app.models.counterparty_cache import CounterpartyCache

    row = (
        db.query(CounterpartyCache)
        .filter(CounterpartyCache.tenant_id == tenant_id)
        .first()
    )
    if not row or not row.data:
        return ""
    items = row.data if isinstance(row.data, list) else []
    cp_key = normalize_counterparty_id(counterparty_id)
    for cp in items:
        if not isinstance(cp, dict):
            continue
        if normalize_counterparty_id(str(cp.get("id") or "")) != cp_key:
            continue
        return (cp.get("email") or "").strip()
    return ""


@router.post("/send-email", response_model=InvoiceEmailSendResponse)
def send_invoice_email(
    data: InvoiceEmailSendRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора (tenant)")

    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    smtp_host = (tenant.smtp_host or "").strip()
    smtp_user = (tenant.smtp_username or "").strip()
    smtp_pass = (tenant.smtp_password or "").strip()
    if not smtp_host or not smtp_user or not smtp_pass:
        raise HTTPException(
            status_code=400,
            detail="SMTP не настроен у арендатора.",
        )

    cp_id = (data.counterparty_id or "").strip()
    if not cp_id:
        raise HTTPException(status_code=400, detail="Укажите counterparty_id")

    to_email = (data.email or "").strip()
    if not to_email:
        to_email = _counterparty_email_from_cache(db, tenant_id, cp_id)
    if not to_email or "@" not in to_email:
        raise HTTPException(
            status_code=400,
            detail="У контрагента нет email. Укажите почту в 1С.",
        )

    invoice_id = (data.invoice_id or "").strip() or None
    service_type = (data.service_type or "").strip().lower() or None
    integration = get_integration_for_tenant(db, tenant_id)
    file_path = None
    try:
        if not invoice_id and service_type:
            invoice_id = find_invoice_id_for_service_type(
                integration, cp_id, service_type, tenant=tenant
            )
        if not invoice_id:
            invoice_id = find_latest_invoice_id(integration, cp_id)
        if not invoice_id:
            raise HTTPException(
                status_code=404,
                detail="Не найден счёт для этого контрагента",
            )

        try:
            resolve_invoice_for_counterparty(
                integration,
                invoice_id,
                cp_id,
                db=db,
                tenant_id=tenant_id,
            )
        except HTTPException:
            raise
        except Exception:
            pass

        download_error = None
        try:
            file_path = integration.get_invoice_and_download(invoice_id, tenant=tenant)
        except Exception as exc:
            download_error = str(exc)
            logger.warning("Email invoice download failed %s: %s", invoice_id, exc)
        if not file_path:
            file_path = find_cached_invoice_pdf(invoice_id, db=db, tenant_id=tenant_id)
        if not file_path:
            detail = f"Не удалось получить PDF счёта {invoice_id} из 1С."
            if download_error:
                detail = f"{detail} Причина: {download_error}"
            raise HTTPException(status_code=502, detail=detail)

        cp_name = (data.counterparty_name or "").strip() or cp_id
        svc_ru = service_type_label(service_type)
        subject = f"Счёт на оплату — {tenant.name or tenant.legal_name or 'ТРЦ'}"
        body = (
            f"Добрый день!\n\n"
            f"{('Контрагент: ' + cp_name + '.') if cp_name and cp_name != cp_id else ''}\n"
            f"Направляем вам счёт на оплату"
            f"{f' ({svc_ru})' if svc_ru else ''}.\n"
            f"Подробности во вложении.\n\n"
            f"С уважением,\n{tenant.name or tenant.legal_name or 'ТРЦ'}\n"
        ).replace("\n\n\n", "\n\n")
        result = send_smtp_email_with_attachment(
            host=smtp_host,
            port=int(tenant.smtp_port or 587),
            username=smtp_user,
            password=smtp_pass,
            to_email=to_email,
            subject=subject,
            body=body,
            attachment_path=file_path,
            attachment_filename=f"invoice_{invoice_id}.pdf",
            use_starttls=bool(
                True if tenant.smtp_use_starttls is None else tenant.smtp_use_starttls
            ),
            from_email=(tenant.smtp_from_email or smtp_user).strip(),
        )
        if not result.get("ok"):
            raise HTTPException(
                status_code=502,
                detail=result.get("error") or "Не удалось отправить письмо",
            )
        return InvoiceEmailSendResponse(
            ok=True,
            message=result.get("message") or f"Счёт отправлен на {to_email}",
            email=to_email,
            invoice_id=invoice_id,
        )
    finally:
        if integration and hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass


def _resolve_xlsx_payment_for_send(
    db: Session,
    tenant_id: Optional[int],
    *,
    payment,
    counterparty_id: Optional[str],
    service_type: Optional[str],
    one_c_available: bool,
):
    """Whether send_notification should go through the xlsx PDF path
    (app/services/xlsx_invoice_pdf.py) instead of any 1C download — see
    that module's docstring for why an xlsx-sourced row can never be
    resolved through the 1C-only helpers below it here
    (resolve_invoice_for_counterparty, find_invoice_id_for_service_type,
    ...): they all search live 1C invoice lists for a real GUID, and an
    xlsx row's synthetic "xlsx:..." id will never be in one.

    Two cases:
    - `payment` was already resolved (via payment_id) and IS an xlsx row —
      always honored, regardless of whether this tenant also happens to
      have a live 1C connection (a mixed tenant can have both kinds of
      rows for different periods/counterparties).
    - No specific payment was requested, but 1C is unavailable for this
      tenant — best-effort DB lookup by counterparty (+service_type), the
      xlsx equivalent of find_invoice_id_for_service_type/
      find_latest_invoice_id. Deliberately never runs when 1C IS
      available, so a hybrid tenant's live 1C invoice for this
      counterparty/service_type is never shadowed by a possibly-stale
      xlsx row found instead.
    """
    if payment is not None:
        return payment if payment.source == "xlsx" else None
    if one_c_available or not counterparty_id:
        return None
    return find_latest_xlsx_payment(db, tenant_id, counterparty_id, service_type=service_type)


@router.get("/preview-message", response_model=MessagePreviewResponse)
def preview_message(
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    payment_id: Optional[int] = Query(None, description="Тот же payment_id, что и в реальной отправке"),
    notification_type: NotificationType = Query(..., description="Какое напоминание смотрим (Первое/За 3 дня/В день/Просрочено)"),
    service_type: Optional[str] = Query(None, description="rent | utilities | operations"),
    counterparty_name: Optional[str] = Query(None),
    invoice_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Запрошено 2026-09-02 (после того, как в реальном ручном сообщении
    Maxi Mall нашлись сразу 3 реальные ошибки — не тот месяц, не тот
    период, ложное "просрочено") — посмотреть текст сообщения ДО отправки,
    без единого побочного эффекта: build_whatsapp_message ничего не
    коммитит в базу и не ходит в WhatsApp, просто строит строку. Не
    занимает send-slot (reserve_send_slot тут не вызывается вообще) —
    можно вызывать сколько угодно раз подряд, реальная отправка потом
    увидит те же кандидаты, как будто preview не было."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора (tenant)")
    message = build_whatsapp_message(
        db,
        tenant_id=tenant_id,
        payment_id=payment_id,
        notification_type=notification_type,
        counterparty_name=counterparty_name,
        invoice_number=invoice_number,
        service_type=service_type,
    )
    return MessagePreviewResponse(message=message)


@router.post("/send-quick-message", response_model=QuickMessageSendResponse)
def send_quick_message(
    data: QuickMessageSendRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Быстрое сообщение без счёта/PDF — со страницы контрагента, из
    клиентских шаблонов (см. lib/quickMessageTemplates.ts). Не создаёт
    Notification (payment_id там NOT NULL, а здесь платежа нет) — эти
    отправки поэтому не попадают в /whatsapp-log, тот читает только
    Notification/AutoNotificationLog; принято сознательно, чтобы не
    заводить отдельную миграцию под 3-4 шаблона (см. обсуждение с
    пользователем 2026-09-18)."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора (tenant)")
    assert_phone_allowed_for_counterparty(
        db,
        tenant_id,
        data.counterparty_id,
        data.phone_number,
        integration=get_integration_for_tenant(db, tenant_id),
    )
    from app.services.tenant_whatsapp import get_whatsapp_for_tenant

    whatsapp = get_whatsapp_for_tenant(db, tenant_id)
    success = whatsapp.send_message(phone_number=data.phone_number, message=data.message)
    if not success:
        return QuickMessageSendResponse(success=False, error="Не удалось отправить сообщение через WhatsApp")
    return QuickMessageSendResponse(success=True)


@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    data: NotificationSend,
    background_tasks: BackgroundTasks,
    invoice_id: Optional[str] = Query(None, description="Invoice ID from 1C to download and send"),
    immediate: bool = Query(
        False,
        description=(
            "Сразу отправить в WhatsApp синхронно (без очереди Kafka), в этом же "
            "HTTP-запросе. По умолчанию False — через Kafka (или фон, если Kafka "
            "недоступна), так безопаснее: True блокирует обработку запроса на время "
            "вызова Green API. Передавайте True только для разовой ручной диагностики."
        ),
    ),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    counterparty_id: Optional[str] = Query(
        None, description="UUID контрагента — счёт и телефон только его"
    ),
    counterparty_name: Optional[str] = Query(None, description="Имя контрагента для шаблона"),
    db: Session = Depends(get_db)
):

    notification_service = NotificationService(db)
    file_path = None

    from app.models.payment import TenantPayment

    counterparty_id = counterparty_id or data.counterparty_id
    invoice_id = invoice_id or data.invoice_id

    payment = None
    if data.payment_id:
        payment = db.query(TenantPayment).filter(TenantPayment.id == data.payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail="Платёж не найден")
        # payment_id came straight from the client (or, for xlsx rows, is
        # trusted as-is by the branch below with no live-1C round-trip to
        # incidentally catch a mismatch) — found 2026-08-31 while adding the
        # xlsx send path: without this check, a tenant/TRC login scoped to
        # tenant A could pass tenant B's payment_id and have A's own tenant
        # record used as the invoice's supplier while B's counterparty/amount
        # data got sent out. tenant_id is None only for an unrestricted admin
        # request (see resolve_tenant_id) — same meaning as everywhere else
        # this dependency feeds into.
        if tenant_id is not None and payment.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Платёж не принадлежит этому арендатору")
        if not invoice_id and payment.invoice_id:
            invoice_id = payment.invoice_id
        if not counterparty_id and payment.counterparty_id:
            counterparty_id = payment.counterparty_id

    if not counterparty_id:
        raise HTTPException(
            status_code=400,
            detail="Укажите counterparty_id (контрагент из 1С для привязки счёта)",
        )

    integration = get_integration_for_tenant(db, tenant_id)
    tenant = get_tenant_by_id(db, tenant_id)
    defer_pdf_to_worker = bool(tenant and tenant_uses_nova_org(tenant))
    payment_service = PaymentService(db, tenant_id=tenant_id)
    try:
        xlsx_payment = _resolve_xlsx_payment_for_send(
            db,
            tenant_id,
            payment=payment,
            counterparty_id=counterparty_id,
            service_type=data.service_type,
            one_c_available=bool(integration.client),
        )
        if xlsx_payment is not None:
            if tenant is None:
                raise HTTPException(status_code=404, detail="Арендатор не найден")
            assert_phone_allowed_for_counterparty(
                db,
                tenant_id,
                xlsx_payment.counterparty_id,
                data.phone_number,
                integration=None,
            )
            try:
                file_path = render_xlsx_invoice_pdf(db, xlsx_payment, tenant)
            except MissingSupplierRequisitesError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if not file_path or not os.path.exists(file_path):
                raise HTTPException(
                    status_code=502,
                    detail="Не удалось сформировать PDF счёта из данных Excel.",
                )
            payment = xlsx_payment
            invoice_id = xlsx_payment.invoice_id
            counterparty_id = xlsx_payment.counterparty_id
            data = data.model_copy(
                update={
                    "payment_id": xlsx_payment.id,
                    "invoice_id": invoice_id,
                    "counterparty_id": counterparty_id,
                }
            )
        elif not integration.client:
            cached_pdf = (
                find_cached_invoice_pdf(invoice_id, db=db, tenant_id=tenant_id)
                if invoice_id
                else None
            )
            if invoice_id and counterparty_id and cached_pdf:
                logger.warning(
                    "1C unavailable; sending cached PDF for invoice %s (%s)",
                    invoice_id,
                    integration.unavailable_message(),
                )
                file_path = cached_pdf
                assert_phone_allowed_for_counterparty(
                    db,
                    tenant_id,
                    counterparty_id,
                    data.phone_number,
                    integration=None,
                )
                if not payment and data.payment_id:
                    payment = db.query(TenantPayment).filter(
                        TenantPayment.id == data.payment_id
                    ).first()
                if not payment:
                    cp_key = normalize_counterparty_id(counterparty_id)
                    payment = (
                        db.query(TenantPayment)
                        .filter(
                            func.lower(TenantPayment.invoice_id)
                            == (invoice_id or "").strip().lower(),
                            func.lower(TenantPayment.counterparty_id) == cp_key,
                        )
                        .first()
                    )
                if payment:
                    data = data.model_copy(update={"payment_id": payment.id})
            else:
                raise HTTPException(
                    status_code=503,
                    detail=integration.unavailable_message(),
                )
        else:
            service_type = (data.service_type or "").strip().lower()

            # payment_trusted вычисляем ДО резолва по service_type — он же
            # определяет, можно ли доверять пришедшему invoice_id.
            payment_trusted = (
                payment
                and payment.invoice_id
                and payment.counterparty_id
                and (
                    not invoice_id
                    or (payment.invoice_id or "").strip().lower()
                    == (invoice_id or "").strip().lower()
                )
                and (
                    not counterparty_id
                    or normalize_counterparty_id(payment.counterparty_id)
                    == normalize_counterparty_id(counterparty_id)
                )
            )

            if service_type and invoice_id and not payment_trusted:
                # invoice_id без привязки к конкретному payment (payment_id не
                # передан/не совпал) может быть устаревшим кэшем "последнего
                # счёта контрагента" с фронта — CounterpartiesTable кладёт туда
                # counterparty.latestInvoice, который обновляется почасовым
                # фоновым синком и не знает про выбранный здесь service_type.
                # Раньше это приводило к тому, что при выборе, например,
                # "коммуналка" реально уходил старый закэшированный счёт за
                # аренду с подписью "Услуга: Коммунальные услуги" — файл не
                # менялся, менялась только подпись. Явно выбранный service_type
                # важнее непроверенного invoice_id — сбрасываем его, чтобы блок
                # ниже пересчитал правильный счёт по service_type.
                logger.info(
                    "Ignoring client-supplied invoice_id=%s (tenant=%s cp=%s): "
                    "not payment-bound, re-resolving by service_type=%s",
                    invoice_id,
                    tenant_id,
                    counterparty_id,
                    service_type,
                )
                invoice_id = None

            if service_type and counterparty_id and not invoice_id:
                if tenant:
                    enabled = tenant_payment_types_enabled(tenant)
                    if not enabled.get(service_type, True):
                        raise HTTPException(
                            status_code=400,
                            detail="Этот вид оплат отключён для арендатора",
                        )
                if not defer_pdf_to_worker:
                    resolved = find_invoice_id_for_service_type(
                        integration,
                        counterparty_id,
                        service_type,
                        tenant=tenant,
                    )
                    if resolved:
                        invoice_id = resolved
                    else:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Счёт для типа «{service_type}» не найден в 1С",
                        )
                else:
                    logger.info(
                        "Nova org tenant %s: подбор счёта service_type=%s — на worker",
                        tenant_id,
                        service_type,
                    )
            if payment_trusted:
                invoice_id = payment.invoice_id
                counterparty_id = payment.counterparty_id
            elif defer_pdf_to_worker and not invoice_id and service_type:
                pass
            else:
                invoice_id, counterparty_id = resolve_invoice_for_counterparty(
                    integration,
                    invoice_id,
                    counterparty_id,
                    db=db,
                    tenant_id=tenant_id,
                    skip_live_1c=defer_pdf_to_worker,
                )
            assert_phone_allowed_for_counterparty(
                db,
                tenant_id,
                counterparty_id,
                data.phone_number,
                integration=None if defer_pdf_to_worker else integration,
            )
            if payment and payment.counterparty_id:
                if (
                    normalize_counterparty_id(payment.counterparty_id)
                    != normalize_counterparty_id(counterparty_id)
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Платёж не соответствует выбранному контрагенту",
                    )
            if not payment:
                if defer_pdf_to_worker and counterparty_id:
                    cp_key = normalize_counterparty_id(counterparty_id)
                    if invoice_id:
                        # func.lower(...) — 1С может отдавать один и тот же
                        # invoice_id в разном регистре из разных методов
                        # (batch-список vs invoice_by_id); точное сравнение
                        # не находило уже существующую строку и создавало
                        # дубликат-заглушку с обнулённой суммой рядом с
                        # настоящим счётом — выглядело как "новый счёт
                        # обнулил старый". Тот же паттерн, что и в sync
                        # (payment_service.py), приводим к единому виду.
                        # tenant_id обязателен и здесь: без него совпадающий
                        # invoice_id+counterparty_id у другого арендатора мог
                        # вернуть/перезаписать чужую строку (тот же класс
                        # бага, что в payment_service.sync_from_1c — см.
                        # аудит от 2026-08-25).
                        payment_query = db.query(TenantPayment).filter(
                            func.lower(TenantPayment.invoice_id)
                            == invoice_id.strip().lower(),
                            func.lower(TenantPayment.counterparty_id) == cp_key,
                        )
                        if tenant_id:
                            payment_query = payment_query.filter(
                                TenantPayment.tenant_id == tenant_id
                            )
                        payment = payment_query.first()
                    if not payment:
                        from datetime import date as date_cls
                        from app.models.payment import PaymentStatus

                        tenant_row = get_tenant_by_id(db, tenant_id)
                        today = date_cls.today()
                        payment = TenantPayment(
                            ip_name=(tenant_row.legal_name if tenant_row else "—"),
                            tenant_name=counterparty_name or counterparty_id,
                            invoice_date=today,
                            due_date=today,
                            period=today.strftime("%Y-%m"),
                            status=PaymentStatus.UNPAID,
                            invoice_id=invoice_id,
                            counterparty_id=counterparty_id,
                            tenant_id=tenant_id,
                        )
                        db.add(payment)
                        db.commit()
                        db.refresh(payment)
                elif invoice_id and counterparty_id:
                    payment = payment_service.ensure_payment_for_counterparty(
                        counterparty_id,
                        invoice_id,
                        integration=integration,
                    )
            data = data.model_copy(
                update={
                    "payment_id": payment.id,
                    "invoice_id": invoice_id,
                    "counterparty_id": counterparty_id,
                    "service_type": service_type or data.service_type,
                }
            )

            if invoice_id and not defer_pdf_to_worker:
                download_error: Optional[str] = None
                try:
                    logger.debug("Downloading invoice %s from 1C...", invoice_id)
                    file_path = integration.get_invoice_and_download(
                        invoice_id, tenant=tenant
                    )
                except Exception as e:
                    download_error = str(e)
                    logger.warning(
                        "Invoice download failed for %s: %s", invoice_id, e
                    )
                if not file_path:
                    cached = find_cached_invoice_pdf(invoice_id, db=db, tenant_id=tenant_id)
                    if cached:
                        logger.warning(
                            "Using cached PDF for invoice %s (1C download unavailable)",
                            invoice_id,
                        )
                        file_path = cached
                if not file_path:
                    detail = (
                        f"Не удалось получить PDF счёта {invoice_id} из 1С для этого арендатора. "
                        "Отправка отменена, чтобы не уйти чужой документ."
                    )
                    if download_error:
                        detail = f"{detail} Причина: {download_error}"
                    raise HTTPException(status_code=502, detail=detail)
            elif invoice_id and defer_pdf_to_worker:
                logger.info(
                    "COM tenant %s: PDF счёта %s — в фоне (WhatsApp worker)",
                    tenant_id,
                    invoice_id,
                )
    finally:
        if integration and hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass

    if invoice_id and not file_path and not defer_pdf_to_worker:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Не удалось получить PDF счёта {invoice_id} из 1С. "
                "Отправка отменена, чтобы не уйти чужой документ."
            ),
        )

    # send_notification может дойти до синхронного requests.post в Green API
    # (immediate=True, или Kafka недоступна/не сконфигурирована) — это async
    # def-хендлер на единственном uvicorn-воркере (без --workers), поэтому
    # блокирующий вызов запускаем в threadpool, а не напрямую на event loop:
    # иначе зависший Green API замораживает весь backend (включая /health) на
    # время таймаута запроса, а не только эту одну отправку.
    notification, queued = await run_in_threadpool(
        notification_service.send_notification,
        data,
        file_path=file_path,
        tenant_id=tenant_id,
        counterparty_name=counterparty_name,
        immediate=immediate and not defer_pdf_to_worker,
        defer_whatsapp=defer_pdf_to_worker,
    )

    if defer_pdf_to_worker and not queued:
        from app.services.whatsapp_jobs import process_whatsapp_job

        job_payload = {
            "type": "whatsapp_send",
            "notification_id": notification.id,
            "tenant_id": tenant_id,
            "payment_id": notification.payment_id,
            "file_path": None,
            "counterparty_name": counterparty_name,
            "invoice_id": invoice_id,
            "counterparty_id": counterparty_id,
            "service_type": (data.service_type or "").strip().lower() or None,
        }
        background_tasks.add_task(process_whatsapp_job, job_payload)
        queued = True

    # До 2026-09-10 успешная синхронная отправка сразу проставляла DELIVERED,
    # так что сравнение с DELIVERED здесь работало как "точно ушло, не failed".
    # Теперь успех оставляет статус SENT (реальная доставка подтверждается
    # только позже, вебхуком outgoingMessageStatus — см.
    # whatsapp_jobs.deliver_notification/_process_green_api_webhook), так что
    # DELIVERED тут почти никогда не наступит синхронно — сравнение нужно
    # менять на "не FAILED", иначе это поле всегда возвращало бы False.
    whatsapp_sent = not queued and notification.status != NotificationStatus.FAILED
    return NotificationResponse.model_validate(notification).model_copy(
        update={"queued": queued, "whatsapp_sent": whatsapp_sent}
    )


@router.post("", response_model=NotificationResponse)
async def create_notification(
    data: NotificationCreate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Низкоуровневое создание записи без резолвинга счёта/телефона — только для
    администратора (ручные корректировки), не для обычного пользовательского потока."""

    notification_service = NotificationService(db)
    notification = notification_service.create_notification(data)
    return notification


@router.post("/send-file")
async def send_file_via_whatsapp(
    file: UploadFile = File(...),
    phone_number: str = Form(...),
    invoice_id: Optional[str] = Form(None),
    counterparty_id: Optional[str] = Form(None),
    tenant_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
):

    tenant_id = resolve_tenant_id(db, tenant_id, credentials)

    try:
        if not counterparty_id:
            raise HTTPException(
                status_code=400,
                detail="Укажите counterparty_id — файл счёта только для этого контрагента",
            )
        integration = get_integration_for_tenant(db, tenant_id)
        try:
            if not integration.client:
                raise HTTPException(status_code=503, detail="1C client not available")
            if invoice_id:
                from app.services.invoice_access import assert_invoice_belongs_to_counterparty

                assert_invoice_belongs_to_counterparty(
                    integration, invoice_id, counterparty_id
                )
            assert_phone_allowed_for_counterparty(
                db,
                tenant_id,
                counterparty_id,
                phone_number,
                integration=integration,
            )
        finally:
            if integration and hasattr(integration, "close"):
                try:
                    integration.close()
                except Exception:
                    pass

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1] if file.filename else '.pdf') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        

        from app.services.message_builder import build_whatsapp_message
        from app.services.job_queue import enqueue_whatsapp_job
        from app.services.whatsapp_jobs import deliver_raw_message, persist_outbox_file

        message = build_whatsapp_message(
            db,
            tenant_id=tenant_id,
            invoice_number=invoice_id or None,
        )

        outbox_path = persist_outbox_file(tmp_file_path)
        try:
            os.unlink(tmp_file_path)
        except OSError:
            pass

        job = {
            "type": "whatsapp_file",
            "tenant_id": tenant_id,
            "phone_number": phone_number,
            "message": message,
            "file_path": outbox_path,
            "file_base64": base64.b64encode(content).decode("ascii"),
            "file_name": file.filename or "invoice.pdf",
            "invoice_id": invoice_id,
            "counterparty_id": counterparty_id,
        }
        if settings.KAFKA_ENABLED:
            # KafkaProducer.send/flush блокирует (см. job_queue.publish, до 15с) —
            # без threadpool это подвешивает единственный uvicorn-воркер
            # (см. аудит от 2026-08-25).
            queued = await run_in_threadpool(enqueue_whatsapp_job, job)
            if queued:
                return {
                    "success": True,
                    "message": "Файл поставлен в очередь Kafka на отправку",
                    "queued": True,
                }

        # Тот же риск, что у /send: без Kafka это синхронный Green API вызов —
        # уводим его в threadpool, чтобы не подвесить event loop единственного
        # uvicorn-воркера, если Kafka временно недоступна.
        success = await run_in_threadpool(
            deliver_raw_message,
            db,
            tenant_id=tenant_id,
            phone_number=phone_number,
            message=message,
            file_path=outbox_path,
            counterparty_id=counterparty_id,
        )
        if success:
            return {"success": True, "message": "File sent successfully", "queued": False}
        return {"success": False, "message": "Failed to send file", "queued": False}
            
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error sending file via WhatsApp (tenant_id=%s)", tenant_id)
        return {"success": False, "message": "Не удалось отправить файл. Попробуйте позже."}


@router.post("/test")
async def test_whatsapp_message(
    phone_number: str = Form(..., description="Phone number to send test message to"),
    message: Optional[str] = Form("Тестовое сообщение из системы", description="Test message text"),
    _: AdminUser = Depends(get_current_admin),
):
    """Диагностика конфигурации Green API — только для администратора: без
    авторизации это был открытый релей на отправку WhatsApp на любой номер."""

    try:
        whatsapp = WhatsAppService()
        

        if not whatsapp.api_token and not whatsapp.test_api_token:
            return {
                "success": False,
                "message": "Green API not configured. Set GREEN_API_ID_INSTANCE and GREEN_API_API_TOKEN in .env",
                "config": {
                    "provider": "green-api",
                    "has_api_token": bool(whatsapp.api_token),
                    "id_instance": whatsapp.id_instance,
                    "test_id_instance": whatsapp.test_id_instance,
                    "api_url": whatsapp.api_url,
                },
            }

        if not whatsapp.id_instance and not whatsapp.test_id_instance:
            return {
                "success": False,
                "message": "Green API idInstance not configured. Set GREEN_API_ID_INSTANCE in .env",
                "config": {
                    "provider": "green-api",
                    "has_api_token": bool(whatsapp.api_token),
                    "id_instance": whatsapp.id_instance,
                    "test_id_instance": whatsapp.test_id_instance,
                },
            }
        
        success = await run_in_threadpool(
            whatsapp.send_message,
            phone_number=phone_number,
            message=message,
        )
        
        if success:
            return {
                "success": True,
                "message": "Test message sent successfully",
                "config": {
                    "provider": "green-api",
                    "id_instance": whatsapp.id_instance,
                    "recipient": phone_number,
                },
            }
        else:
            return {
                "success": False,
                "message": "Failed to send test message. Check logs for details.",
                "config": {
                    "provider": "green-api",
                    "id_instance": whatsapp.id_instance,
                },
            }
            
    except Exception:
        logger.exception("Error in test WhatsApp endpoint")
        return {
            "success": False,
            "message": "Не удалось отправить тестовое сообщение. Проверьте логи сервера.",
        }
