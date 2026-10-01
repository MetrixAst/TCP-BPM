from fastapi import APIRouter, Depends, Query, Body, HTTPException
from fastapi.concurrency import run_in_threadpool
from app.api.tenant_scope import scoped_tenant_id
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from app.db.database import get_db
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id
from pydantic import BaseModel
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Ответ клиенту при сбое интеграции с 1С — без деталей исключения (URL, причина
# авторизации и т.п.); полная трассировка уходит только в лог сервера.
_ONE_C_ERROR_MESSAGE = "Не удалось получить данные из 1С. Попробуйте позже или обратитесь к администратору."

router = APIRouter()


class ConfirmRequest(BaseModel):
    received_ids: List[str]
    status: str = "sent"
    errors: List[str] = []
    sync_token: Optional[str] = None


@router.get("/data")
async def get_1c_data(
    limit: int = Query(100, ge=1, le=1000, description="Количество записей (макс 1000)"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db)
):

    integration = None
    try:
        logger.debug(f" Request to get 1C data. Limit: {limit}, tenant_id: {tenant_id}")
        integration = get_integration_for_tenant(db, tenant_id)
        
        if not integration.client:
            logger.debug(" 1C client not available")
            return {"error": "1C client not available", "data": [], "has_more": False, "sync_token": None}
        

        if not integration.client.access_token:
            logger.debug(" No access token, attempting to authenticate...")
            try:
                integration.client.authenticate()
                logger.debug(f" Authenticated. Token: {integration.client.access_token[:20] if integration.client.access_token else 'None'}...")
            except Exception as auth_error:
                logger.debug(f" Authentication failed: {auth_error}")
                return {"error": f"Authentication failed: {str(auth_error)}", "data": [], "has_more": False, "sync_token": None}
        

        logger.debug(f" Fetching data from 1C queue with limit {limit}")
        data_response = integration.client.get_data(limit=limit)
        logger.debug(f" Received {len(data_response.data)} records from 1C")
        

        result = []
        for record in data_response.data:
            result.append({
                "id": record.id,
                "type": record.type,
                "data": record.data
            })
        
        logger.debug(f" Returning {len(result)} records")
        payload = {
            "data": result,
            "has_more": data_response.has_more,
            "sync_token": data_response.sync_token,
        }
        warning = integration.get_client_warning()
        if warning and not result:
            payload["warning"] = warning
        return payload
    except Exception:
        logger.exception("Error getting data from 1C (tenant_id=%s)", tenant_id)
        return {"error": _ONE_C_ERROR_MESSAGE, "data": [], "has_more": False, "sync_token": None}
    finally:
        if integration and hasattr(integration, 'close'):
            try:
                integration.close()
            except Exception:
                pass


@router.get("/balance")
async def get_1c_balance(
    counterparty_id: str = Query(..., description="UUID контрагента"),
    since: Optional[str] = Query(None, description="Дата на которую нужен баланс (YYYY-MM-DDT:00:00:00)"),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db)
):

    integration = None
    try:
        logger.debug(f" Request to get 1C balance. Counterparty: {counterparty_id}, Since: {since}, tenant_id: {tenant_id}")
        integration = get_integration_for_tenant(db, tenant_id)
        
        if not integration.client:
            logger.debug(" 1C client not available")
            return {"error": "1C client not available"}
        

        if not integration.client.access_token:
            logger.debug(" No access token, attempting to authenticate...")
            try:
                integration.client.authenticate()
                logger.debug(f" Authenticated. Token: {integration.client.access_token[:20] if integration.client.access_token else 'None'}...")
            except Exception as auth_error:
                logger.debug(f" Authentication failed: {auth_error}")
                return {"error": f"Authentication failed: {str(auth_error)}"}
        

        since_date = None
        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                try:
                    since_date = datetime.strptime(since, "%Y-%m-%d")
                except ValueError:
                    pass
        

        logger.debug(f"Fetching balance for counterparty {counterparty_id}")
        balance = integration.client.get_balance(counterparty_id, since=since_date)
        logger.debug(f" Received balance data")
        

        result = {
            "counterparty": balance.counterparty,
            "balances": {
                "receivable": balance.balances.receivable,
                "payable": balance.balances.payable,
                "net": balance.balances.net
            },
            "aging": [
                {
                    "period": item.period,
                    "amount": item.amount
                } if hasattr(item, 'period') else item
                for item in balance.aging
            ],
            "documents": balance.documents if balance.documents else balance.by_documents
        }
        

        if balance.by_documents:
            result["by_documents"] = balance.by_documents
        

        if balance.date:
            result["date"] = balance.date
        
        return result
    except Exception:
        logger.exception(
            "Error getting balance from 1C (counterparty_id=%s, tenant_id=%s)",
            counterparty_id,
            tenant_id,
        )
        return {"error": _ONE_C_ERROR_MESSAGE}
    finally:
        if integration and hasattr(integration, 'close'):
            try:
                integration.close()
            except Exception:
                pass


@router.get("/counterparties")
async def get_1c_counterparties(
    limit: int = Query(10000, ge=1, le=50000, description="Макс. записей из 1С (с пагинацией OData)"),
    include_invoice_status: bool = Query(
        False,
        description="Статусы из БД после sync (быстро)",
    ),
    include_contracts: bool = Query(
        False,
        description="Договоры уже в кэше БД (обновляются при sync)",
    ),
    period: Optional[str] = Query(
        None,
        description="Период YYYY-MM для статусов из БД",
    ),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db)
):
    from app.services.counterparty_cache_service import (
        get_counterparties_api_response,
        maybe_schedule_tenant_data_sync,
    )

    try:
        logger.debug(
            " Request to get counterparties from DB cache. Limit: %s, tenant_id: %s",
            limit,
            tenant_id,
        )
        tenant = get_tenant_by_id(db, tenant_id) if tenant_id else None

        if tenant_id:
            # С KAFKA_ENABLED=true уходит в блокирующий KafkaProducer.send().get()
            # (до 15с, см. job_queue.publish) — а это обычный GET, дёргается на
            # каждую загрузку страницы. Без threadpool подвешивает единственный
            # uvicorn-воркер целиком (см. аудит от 2026-08-25).
            await run_in_threadpool(maybe_schedule_tenant_data_sync, db, tenant_id, period)

        integration = get_integration_for_tenant(db, tenant_id) if tenant_id else None
        warning = integration.get_client_warning() if integration else None

        payload = get_counterparties_api_response(
            db,
            tenant_id=tenant_id,
            tenant=tenant,
            limit=limit,
            include_invoice_status=include_invoice_status,
            period=period,
            warning=warning,
        )

        if include_contracts is False and payload.get("counterparties"):
            for cp in payload["counterparties"]:
                cp.pop("contracts", None)

        logger.debug(
            " Returning %s counterparties from DB cache (sync_status=%s)",
            len(payload.get("counterparties") or []),
            payload.get("sync_status"),
        )
        return payload
    except Exception:
        logger.exception("Error getting counterparties from cache (tenant_id=%s)", tenant_id)
        return {"error": _ONE_C_ERROR_MESSAGE, "counterparties": []}


@router.post("/counterparties/sync")
async def sync_1c_counterparties(
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db),
):
    """Постановка загрузки контрагентов из 1С в кэш БД (фон / Kafka), без долгого HTTP."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Выберите арендатора")

    from app.services.counterparty_cache_service import request_counterparty_cache_sync

    if not await run_in_threadpool(request_counterparty_cache_sync, db, tenant_id):
        return {
            "ok": False,
            "count": 0,
            "status": "running",
            "error": "Синхронизация уже выполняется, подождите",
        }
    return {
        "ok": True,
        "count": 0,
        "status": "started",
        "message": "Синхронизация запущена. Опросите список контрагентов (sync_status).",
    }


@router.post("/confirm")
async def confirm_1c_data(
    request: ConfirmRequest,
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    db: Session = Depends(get_db)
):

    integration = None
    try:
        logger.debug(f" Request to confirm 1C data. IDs: {len(request.received_ids)}, Status: {request.status}, tenant_id: {tenant_id}")
        integration = get_integration_for_tenant(db, tenant_id)
        
        if not integration.client:
            logger.debug(" 1C client not available")
            return {"error": "1C client not available", "success": False}
        

        if not integration.client.access_token:
            logger.debug("No access token, attempting to authenticate...")
            try:
                integration.client.authenticate()
                logger.debug(f"Authenticated. Token: {integration.client.access_token[:20] if integration.client.access_token else 'None'}...")
            except Exception as auth_error:
                logger.debug(f"Authentication failed: {auth_error}")
                return {"error": f"Authentication failed: {str(auth_error)}", "success": False}
        

        logger.debug(f"Confirming receipt of {len(request.received_ids)} records")
        confirm_response = integration.client.confirm(
            received_ids=request.received_ids,
            status=request.status,
            errors=request.errors,
            sync_token=request.sync_token
        )
        logger.debug(f"Confirmed: {confirm_response.confirmed} records, Failed: {confirm_response.failed}")
        
        return {
            "success": confirm_response.success,
            "confirmed": confirm_response.confirmed,
            "failed": confirm_response.failed
        }
    except Exception:
        logger.exception("Error confirming data in 1C (tenant_id=%s)", tenant_id)
        return {"error": _ONE_C_ERROR_MESSAGE, "success": False}
    finally:
        if integration and hasattr(integration, 'close'):
            try:
                integration.close()
            except Exception:
                pass
