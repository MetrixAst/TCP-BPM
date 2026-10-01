from fastapi import APIRouter, Depends, Query, Response, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from app.api.tenant_scope import scoped_tenant_id
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from datetime import date
from app.core.config import settings
from app.db.database import get_db
from app.services import payment_sync_status
from app.services.job_queue import enqueue_payment_sync
from app.services.payment_sync_jobs import run_payment_sync
from app.schemas.payment import PaymentListResponse, PaymentWithNotifications, PaymentFilter, PaymentAnalytics
from app.schemas.notification import NotificationResponse
from app.services.payment_service import PaymentService
from app.client_1c.exceptions import MissingSupplierRequisitesError, ValidationError
from app.services.nova_1c_service import Nova1CServiceError
from app.services.notification_service import NotificationService
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id
from app.services.tenant_context import apply_tenant_to_filters
from app.services.invoice_access import (
    assert_invoice_belongs_to_counterparty,
    filter_invoices_by_counterparty,
)
from app.models.payment import PaymentStatus, TenantPayment
from app.services.xlsx_invoice_pdf import assert_xlsx_payment_accessible, render_xlsx_invoice_pdf
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from io import BytesIO
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_period(period: str) -> None:
    if not period or len(period) != 7 or period[4] != "-":
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")


def _run_payment_sync_background(
    tenant_id: Optional[int],
    period: str,
    sync_counterparties: bool = True,
) -> None:
    # Сначала контрагенты (id), потом счета с привязкой.
    if sync_counterparties and tenant_id:
        try:
            from app.services.counterparty_cache_service import run_counterparty_cache_sync

            run_counterparty_cache_sync(tenant_id)
        except Exception:
            pass
    try:
        run_payment_sync(tenant_id, period)
    except Exception:
        pass

def _invoices_json(**payload) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(payload))


def _serialize_invoice_row(invoice) -> dict:
    cp_name = invoice.counterparty_name
    cp_id = invoice.counterparty_id
    cp_bin = ""
    if invoice.counterparty and isinstance(invoice.counterparty, dict):
        cp_name = cp_name or invoice.counterparty.get("name", "")
        cp_id = cp_id or invoice.counterparty.get("id", "")
        cp_bin = invoice.counterparty.get("bin", "") or ""

    status_display = invoice.status
    if str(status_display).lower() in ("posted", "true"):
        status_display = "posted"
    elif str(status_display).lower() == "false":
        status_display = "draft"
    # Пусто (Nova/COM — нет надёжного аналога "Проведен" в onec.buh.invoices,
    # см. nova_buh_1c_client.py) намеренно не мапится на "draft" — это не то же
    # самое, что "точно черновик", а "мы не знаем".

    row = {
        "id": str(invoice.id or ""),
        "number": str(invoice.number or ""),
        "date": str(invoice.date or ""),
        "counterparty_name": cp_name or "",
        "counterparty_id": cp_id or "",
        "counterparty": {
            "id": cp_id or "",
            "name": cp_name or "",
            "bin": cp_bin or "",
        },
        "amount": float(invoice.amount or 0),
        "currency": str(invoice.currency or "KZT"),
        "status": str(status_display or ""),
        "pdf": invoice.pdf,
        "items": [
            {
                "name": str(item.name or ""),
                "quantity": float(item.quantity or 0),
                "price": float(item.price or 0),
                "amount": float(item.amount or 0),
            }
            for item in (invoice.items or [])
        ],
    }
    if invoice.vat is not None:
        row["vat"] = float(invoice.vat)
    if invoice.paid_amount is not None:
        row["paid_amount"] = float(invoice.paid_amount)
    return row


@router.get("", response_model=PaymentListResponse)
async def get_payments(
    period: Optional[str] = Query(None, description="Period in format YYYY-MM"),
    date_from: Optional[date] = Query(None, description="Invoice date from (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Invoice date to (YYYY-MM-DD)"),
    ip_name: Optional[str] = Query(None, description="IP name filter"),
    tenant_name: Optional[str] = Query(None, description="Tenant name filter"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    status: Optional[str] = Query(None, description="Payment status (paid, unpaid, overdue, test)"),
    service_type: Optional[str] = Query(
        None, description="rent | utilities | operations | signage | assp"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=1000),
    db: Session = Depends(get_db)
):

    status_enum = None
    if status and status != "test":
        try:
            status_enum = PaymentStatus(status)
        except ValueError:
            status_enum = None

    filters = PaymentFilter(
        period=period,
        date_from=date_from,
        date_to=date_to,
        ip_name=ip_name,
        tenant_name=tenant_name,
        status=status_enum if status != "test" else None,
        service_type=service_type,
        page=page,
        page_size=page_size
    )
    filters = apply_tenant_to_filters(db, tenant_id, filters, ip_name, tenant_name)
    
    payment_service = PaymentService(db, tenant_id=tenant_id)
    notification_service = NotificationService(db)

    is_test = payment_service.is_test_mode(filters, status)
    logger.info(f"Test mode: {is_test}, filters: {filters}, status: {status}")

    payments, total = payment_service.get_payments(filters, status)
    logger.info(f"Payments returned: {len(payments)}, total: {total}")

    # Один batched-запрос на всю страницу вместо запроса на каждый payment.id —
    # раньше это было до page_size (макс. 10000) отдельных SELECT-ов.
    if is_test:
        notifications_by_payment: dict[int, list] = {}
    else:
        notifications_by_payment = notification_service.get_notifications_by_payments(
            [payment.id for payment in payments]
        )

    items = []
    for payment in payments:

        if is_test:
            notifications = payment_service.get_test_notifications(payment.id)
        else:
            notifications = notifications_by_payment.get(payment.id, [])

        try:

            payment_dict = PaymentWithNotifications.model_validate(payment)
            payment_dict.notifications = [NotificationResponse.model_validate(n) for n in notifications]
            items.append(payment_dict)
        except Exception as e:

            logger.error(f"Error serializing payment {payment.id}: {e}", exc_info=True)

            payment_dict = PaymentWithNotifications(
                id=payment.id,
                ip_name=payment.ip_name,
                tenant_name=payment.tenant_name,
                invoice_date=payment.invoice_date,
                due_date=payment.due_date,
                paid_at=payment.paid_at,
                status=payment.status,
                period=payment.period,
                amount=payment.amount,
                paid_amount=payment.paid_amount,
                invoice_id=payment.invoice_id,
                counterparty_id=payment.counterparty_id,
                service_type=payment.service_type,
                notifications=[NotificationResponse.model_validate(n) for n in notifications]
            )
            items.append(payment_dict)
    
    total_pages = (total + page_size - 1) // page_size
    
    return PaymentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/analytics", response_model=PaymentAnalytics)
async def get_analytics(
    period: Optional[str] = Query(None, description="Period in format YYYY-MM"),
    date_from: Optional[date] = Query(None, description="Invoice date from (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Invoice date to (YYYY-MM-DD)"),
    ip_name: Optional[str] = Query(None, description="IP name filter"),
    tenant_name: Optional[str] = Query(None, description="Tenant name filter"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    status: Optional[str] = Query(None, description="Payment status (for test mode)"),
    db: Session = Depends(get_db)
):

    status_enum = None
    if status and status != "test":
        try:
            status_enum = PaymentStatus(status)
        except ValueError:
            status_enum = None

    filters = PaymentFilter(
        period=period,
        date_from=date_from,
        date_to=date_to,
        ip_name=ip_name,
        tenant_name=tenant_name,
        status=status_enum if status != "test" else None,
    )
    filters = apply_tenant_to_filters(db, tenant_id, filters, ip_name, tenant_name)
    
    payment_service = PaymentService(db, tenant_id=tenant_id)
    

    is_test = payment_service.is_test_mode(filters, status)

    analytics = payment_service.get_analytics(filters, status)
    return analytics


@router.post("/sync")
async def start_payments_sync(
    background_tasks: BackgroundTasks,
    period: str = Query(..., description="Period YYYY-MM"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Ставит загрузку реестра из 1С в очередь (Kafka) или в фон API — без долгого HTTP."""
    _validate_period(period)
    if not payment_sync_status.set_running(db, tenant_id, period):
        current = payment_sync_status.get_status(db, tenant_id, period) or {}
        return {
            "status": "running",
            "period": period,
            "message": "Синхронизация уже выполняется",
            **{k: v for k, v in current.items() if k != "status"},
        }
    if settings.KAFKA_ENABLED:
        # KafkaProducer.send().get(timeout=15) блокирует — без threadpool
        # подвешивает единственный uvicorn-воркер (см. аудит от 2026-08-25).
        if await run_in_threadpool(enqueue_payment_sync, tenant_id=tenant_id, period=period):
            return {
                "status": "queued",
                "period": period,
                "message": "Синхронизация в очереди. Опросите /api/payments/sync-status.",
            }
        payment_sync_status.set_failed(db, tenant_id, period, "Не удалось поставить задачу в очередь Kafka")
        raise HTTPException(
            status_code=503,
            detail="Очередь синхронизации недоступна. Повторите позже или обратитесь к администратору.",
        )
    background_tasks.add_task(_run_payment_sync_background, tenant_id, period, True)
    return {
        "status": "started",
        "period": period,
        "message": "Синхронизация запущена. Опросите /api/payments/sync-status.",
    }


@router.get("/sync-status")
async def payments_sync_status(
    period: str = Query(..., description="Period YYYY-MM"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    _validate_period(period)
    status = payment_sync_status.get_status(db, tenant_id, period)
    if not status:
        return {"status": "idle", "period": period}
    return status


@router.get("/{payment_id}/notifications")
async def get_payment_notifications(
    payment_id: int,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Требует авторизации (арендатор/ТРЦ/админ, см. scoped_tenant_id) и проверяет,
    что платёж принадлежит запрошенному арендатору — иначе 404, а не чужие
    уведомления/номера телефонов (см. аудит от 2026-08-25: IDOR по payment_id)."""
    payment_service = PaymentService(db, tenant_id=tenant_id)
    payment = payment_service.get_payment_scoped(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    notification_service = NotificationService(db)
    notifications = notification_service.get_notifications_by_payment(payment_id)
    return notifications


@router.get("/export")
async def export_payments(
    period: Optional[str] = Query(None, description="Period in format YYYY-MM"),
    date_from: Optional[date] = Query(None, description="Invoice date from (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Invoice date to (YYYY-MM-DD)"),
    ip_name: Optional[str] = Query(None, description="IP name filter"),
    tenant_name: Optional[str] = Query(None, description="Tenant name filter"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    status: Optional[str] = Query(None, description="Payment status (paid, unpaid, overdue, test)"),
    db: Session = Depends(get_db)
):

    status_enum = None
    if status and status != "test":
        try:
            status_enum = PaymentStatus(status)
        except ValueError:
            status_enum = None
    
    filters = PaymentFilter(
        period=period,
        date_from=date_from,
        date_to=date_to,
        ip_name=ip_name,
        tenant_name=tenant_name,
        status=status_enum if status != "test" else None,
        page=1,
        page_size=10000
    )
    filters = apply_tenant_to_filters(db, tenant_id, filters, ip_name, tenant_name)
    
    payment_service = PaymentService(db, tenant_id=tenant_id)

    export_rows = payment_service.get_export_rows(filters, status)

    wb = Workbook()
    ws = wb.active
    ws.title = "Реестр оплат"
    

    headers = [
        "ИП", "Арендатор", "Дата выставления счета",
        "Крайний срок оплаты", "Статус оплаты", "Дата оплаты", "Сумма",
        "Тип оплат",
    ]
    

    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
    

    status_translation = {
        "paid": "Оплачено",
        "partial": "Оплачено частично",
        "unpaid": "Не оплачено",
        "overdue": "Просрочено"
    }
    
    def _excel_date(value) -> str:
        if not value:
            return "-"
        if hasattr(value, "strftime"):
            return value.strftime("%d.%m.%Y")
        return str(value)

    for row_idx, row_data in enumerate(export_rows, 2):
        ws.cell(row=row_idx, column=1, value=row_data.get("ip_name") or "—")
        ws.cell(row=row_idx, column=2, value=row_data.get("tenant_name") or "—")
        ws.cell(row=row_idx, column=3, value=_excel_date(row_data.get("invoice_date")))
        ws.cell(row=row_idx, column=4, value=_excel_date(row_data.get("due_date")))
        status_val = str(row_data.get("status") or "unpaid")
        ws.cell(
            row=row_idx,
            column=5,
            value=status_translation.get(status_val, status_val),
        )
        ws.cell(row=row_idx, column=6, value=_excel_date(row_data.get("paid_at")))
        amount = row_data.get("amount")
        ws.cell(row=row_idx, column=7, value=amount if amount is not None else "-")
        ws.cell(row=row_idx, column=8, value=row_data.get("payment_type") or "—")

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + col)].width = 20
    

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    

    filename = f"reestr_oplat_{period or 'all'}.xlsx"
    
    return Response(
        content=output.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/1c/invoices")
async def get_1c_invoices(
    period: Optional[str] = Query(None, description="Period in format YYYY-MM"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    counterparty_id: Optional[str] = Query(
        None, description="UUID контрагента — только его счета"
    ),
    limit: int = Query(10000, ge=1, le=50000, description="Макс. счетов"),
    source: str = Query(
        "db",
        description="db — из PostgreSQL (быстро), live — напрямую из 1С",
    ),
    db: Session = Depends(get_db)
):
    integration = None
    try:
        logger.debug(
            "Request to get invoices. period=%s tenant_id=%s source=%s",
            period,
            tenant_id,
            source,
        )

        if source.strip().lower() != "live":
            payment_service = PaymentService(db, tenant_id=tenant_id)
            result = payment_service.list_invoices_from_db(
                period,
                counterparty_id=counterparty_id,
                limit=limit,
            )
            payload: dict = {"invoices": result, "source": "database"}
            if not result:
                payload["warning"] = (
                    "В реестре нет счетов за выбранный период. "
                    "Нажмите «Обновить из 1С» для синхронизации."
                )
            return _invoices_json(**payload)

        integration = get_integration_for_tenant(db, tenant_id)

        if not integration.client:
            return _invoices_json(error="1C client not available", invoices=[])

        if not integration.client.access_token:
            try:
                integration.client.authenticate()
            except Exception as auth_error:
                return _invoices_json(
                    error=f"Authentication failed: {auth_error}",
                    invoices=[],
                )

        from datetime import datetime

        if period:
            year, month = map(int, period.split("-"))
            since_date = datetime(year, month, 1)
        else:
            since_date = datetime(2020, 1, 1)

        invoices = integration.client.get_invoices(since=since_date, limit=limit)
        if counterparty_id:
            invoices = filter_invoices_by_counterparty(invoices, counterparty_id)

        result = [_serialize_invoice_row(invoice) for invoice in invoices]
        payload: dict = {"invoices": result}
        warning = integration.get_client_warning()
        if warning and not result:
            payload["warning"] = warning
        return _invoices_json(**payload)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting invoices from 1C (tenant_id=%s)", tenant_id)
        return _invoices_json(
            error="Не удалось получить счета из 1С. Попробуйте позже.",
            invoices=[],
        )
    finally:
        if integration and hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass


@router.get("/1c/invoices/{invoice_id}/download")
async def download_1c_invoice(
    invoice_id: str,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    counterparty_id: Optional[str] = Query(
        None, description="UUID контрагента — обязателен для проверки доступа к счёту"
    ),
    db: Session = Depends(get_db)
):

    integration = None
    try:
        logger.debug(f" Request to download invoice: {invoice_id}, tenant_id: {tenant_id}")
        integration = get_integration_for_tenant(db, tenant_id)
        tenant = get_tenant_by_id(db, tenant_id)
        
        if not integration.client:
            logger.debug(" 1C client not available")
            return Response(
                content="1C client not available",
                status_code=503,
                media_type="text/plain"
            )
        

        if not integration.client.access_token:
            logger.debug(" No access token, attempting to authenticate...")
            try:
                integration.client.authenticate()
            except Exception as auth_error:
                logger.debug(f" Authentication failed: {auth_error}")
                return Response(
                    content=f"Authentication failed: {str(auth_error)}",
                    status_code=401,
                    media_type="text/plain"
                )
        

        if not counterparty_id:
            raise HTTPException(
                status_code=400,
                detail="Укажите counterparty_id — счёт доступен только владельцу-контрагенту",
            )
        assert_invoice_belongs_to_counterparty(
            integration, invoice_id, counterparty_id
        )

        logger.debug(f" Downloading file for invoice {invoice_id} (counterparty {counterparty_id})")

        file_path = integration.download_invoice_file(invoice_id, tenant=tenant)
        
        if not file_path or not os.path.exists(file_path):
            logger.debug(f" File not found: {file_path}")
            detail = (
                "Не удалось получить PDF счёта. "
                "Для OData печатная форма из 1С не опубликована — "
                "проверьте, что счёт существует (Document_СчетНаОплатуПокупателю). "
                "Установите fpdf2: pip install fpdf2"
            )
            return Response(
                content=detail,
                status_code=404,
                media_type="text/plain; charset=utf-8",
            )
        
        logger.debug(f" File downloaded: {file_path}")
        

        with open(file_path, 'rb') as f:
            file_content = f.read()
        

        filename = os.path.basename(file_path)
        if not filename.endswith('.pdf'):
            filename = f"invoice_{invoice_id}.pdf"
        
        return Response(
            content=file_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValidationError as exc:
        # e.g. invoice_id isn't a valid GUID — reject before it reaches 1C
        # rather than 500ing (see _guid_literal, audit from 2026-08-25).
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        # Real bug found live 2026-08-28: every HTTPException raised inside
        # this try block (missing counterparty_id -> 400, or
        # assert_invoice_belongs_to_counterparty -> 404/403) was falling
        # through to the generic `except Exception` below and coming back
        # as a 500 "Попробуйте позже" — masking the actual reason (e.g.
        # "Счёт не найден в 1С") behind a misleading retry-later message,
        # for every request that legitimately should 4xx, not 5xx.
        raise
    except MissingSupplierRequisitesError as exc:
        logger.warning(
            "PDF blocked: missing supplier requisites tenant_id=%s invoice=%s: %s",
            tenant_id,
            invoice_id,
            exc,
        )
        return Response(
            content=str(exc),
            status_code=422,
            media_type="text/plain; charset=utf-8",
        )
    except Nova1CServiceError as exc:
        logger.warning(
            "PDF unavailable (Nova/1C): tenant_id=%s invoice=%s: %s",
            tenant_id,
            invoice_id,
            exc,
        )
        return Response(
            content=str(exc),
            status_code=503,
            media_type="text/plain; charset=utf-8",
        )
    except Exception:
        logger.exception(
            "Error downloading invoice %s (tenant_id=%s, counterparty_id=%s)",
            invoice_id,
            tenant_id,
            counterparty_id,
        )
        return Response(
            content="Не удалось скачать счёт из 1С. Попробуйте позже.",
            status_code=500,
            media_type="text/plain; charset=utf-8",
        )
    finally:
        if integration and hasattr(integration, 'close'):
            try:
                integration.close()
            except Exception:
                pass


@router.get("/xlsx/{invoice_id}/download")
async def download_xlsx_invoice(
    invoice_id: str,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """PDF for a TenantPayment(source="xlsx") row — see
    app/services/xlsx_invoice_pdf.py for why this is a completely separate
    path from download_1c_invoice above (no real 1C invoice_id to check
    ownership against, no live/cached 1C data involved at all).

    Keyed by the synthetic invoice_id string (e.g. "xlsx:5:2026-08:cp:rent"),
    not the row's integer PK — GET /api/payments/1c/invoices (source=db)
    is what invoice-client's registry actually reads for BOTH one_c and
    xlsx rows (list_invoices_from_db returns "id": payment.invoice_id for
    every row, no source-specific shape) and only ever hands the client
    that string. Matching this endpoint to it means the client can reuse
    the exact same `invoice.id` field it already has, branching only on
    which download endpoint to call based on `source`."""
    payment = (
        db.query(TenantPayment)
        .filter(func.lower(TenantPayment.invoice_id) == invoice_id.strip().lower())
        .first()
    )
    assert_xlsx_payment_accessible(payment, tenant_id)
    tenant = get_tenant_by_id(db, payment.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Арендатор не найден")

    try:
        file_path = render_xlsx_invoice_pdf(db, payment, tenant)
    except MissingSupplierRequisitesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Не удалось сформировать PDF счёта")

    with open(file_path, "rb") as f:
        file_content = f.read()

    filename = os.path.basename(file_path)
    return Response(
        content=file_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
