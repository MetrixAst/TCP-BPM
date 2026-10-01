"""Планирование полного sync арендатора: реестр платежей + кэш контрагентов."""
from __future__ import annotations

import logging
import threading
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import payment_sync_status
from app.services.counterparty_cache_service import current_period
from app.services.job_queue import enqueue_payment_sync

logger = logging.getLogger(__name__)


def _run_sync_without_kafka(tenant_id: int, period: str) -> None:
    from app.services.payment_sync_jobs import run_payment_sync
    from app.services.counterparty_cache_service import run_counterparty_cache_sync

    # Сначала справочник контрагентов (id), потом счета с привязкой по id.
    try:
        run_counterparty_cache_sync(tenant_id)
    except Exception as exc:
        logger.exception("Background counterparty sync failed tenant_id=%s: %s", tenant_id, exc)
    try:
        run_payment_sync(tenant_id, period)
    except Exception as exc:
        logger.exception("Background payment sync failed tenant_id=%s: %s", tenant_id, exc)


def request_tenant_data_sync(
    db: Session,
    tenant_id: int,
    period: Optional[str] = None,
) -> bool:
    """Sync платежей (очередь) + контрагентов. Не блокирует HTTP."""
    period = period or current_period()

    if settings.KAFKA_ENABLED:
        payment_sync_status.set_running(db, tenant_id, period)
        if enqueue_payment_sync(tenant_id=tenant_id, period=period, sync_counterparties=True):
            logger.info(
                "Tenant data sync queued tenant_id=%s period=%s",
                tenant_id,
                period,
            )
            return True
        payment_sync_status.set_failed(db, tenant_id, period, "Kafka enqueue failed")
        return False

    threading.Thread(
        target=_run_sync_without_kafka,
        args=(tenant_id, period),
        daemon=True,
        name=f"tenant-sync-{tenant_id}",
    ).start()
    logger.info("Tenant data sync started in thread tenant_id=%s period=%s", tenant_id, period)
    return True
