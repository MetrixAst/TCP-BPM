
from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.database import SessionLocal
from app.models.catalog import Tenant
from app.services import payment_sync_status
from app.services.payment_service import PaymentService, invalidate_analytics_cache
from app.services.counterparty_cache_service import invalidate_invoice_status_cache

logger = logging.getLogger(__name__)


def _warn_if_empty_sync_looks_wrong(db, tenant_id: Optional[int], period: str, count: int) -> None:
    """A sync that talks to the wrong 1C backend "succeeds" with status=done and
    0 records — that's exactly what happened to ИП MOON for days (2026-08-11):
    no exception anywhere, so nothing short of eyeballing payment_sync_runs would
    have caught it. A tenant with nova_organization_id set is expected to have
    real invoices somewhere in Nova, so 0 records for it is a red flag worth a
    loud, greppable log line — the natural hook for an error-tracking alert once
    one is wired up (see delivery plan, "тихие провалы")."""
    if count != 0 or not tenant_id:
        return
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant and tenant.nova_organization_id:
        logger.warning(
            "[SYNC-ANOMALY] tenant_id=%s (nova_organization_id=%s) period=%s "
            "synced 0 records despite having a configured Nova org — check "
            "one_c_connection_mode before assuming there's simply no data.",
            tenant_id,
            tenant.nova_organization_id,
            period,
        )


def run_payment_sync(tenant_id: Optional[int], period: str) -> int:
    db = SessionLocal()
    try:
        payment_service = PaymentService(db, tenant_id=tenant_id)
        payments = payment_service.sync_from_1c(period)
        count = len(payments)
        invalidate_analytics_cache(tenant_id, period)
        payment_service.warm_analytics_cache(period)
        invalidate_invoice_status_cache(tenant_id, period)
        payment_sync_status.set_done(db, tenant_id, period, count)
        logger.info(
            "Payment sync done tenant_id=%s period=%s records=%s",
            tenant_id,
            period,
            count,
        )
        _warn_if_empty_sync_looks_wrong(db, tenant_id, period, count)
        return count
    except Exception as exc:
        logger.exception("Payment sync failed tenant_id=%s period=%s", tenant_id, period)
        payment_sync_status.set_failed(db, tenant_id, period, str(exc))
        raise
    finally:
        db.close()


def process_payment_sync_job(payload: dict[str, Any]) -> None:
    tenant_id = payload.get("tenant_id")
    if tenant_id is not None:
        tenant_id = int(tenant_id)
    job_type = str(payload.get("type") or "payment_sync")

    if job_type == "counterparty_sync":
        if not tenant_id:
            logger.warning("Counterparty sync job missing tenant_id job_id=%s", payload.get("job_id"))
            return
        from app.services.counterparty_cache_service import run_counterparty_cache_sync

        run_counterparty_cache_sync(tenant_id)
        return

    period = str(payload.get("period") or "")
    if not period:
        logger.warning("Payment sync job missing period job_id=%s", payload.get("job_id"))
        return
    # Сначала контрагенты + id, затем реестр счетов (привязка по counterparty_id).
    if payload.get("sync_counterparties", True) and tenant_id:
        from app.services.counterparty_cache_service import run_counterparty_cache_sync

        try:
            run_counterparty_cache_sync(tenant_id)
        except Exception:
            logger.exception(
                "Counterparty cache sync failed before payment sync tenant_id=%s",
                tenant_id,
            )
    run_payment_sync(tenant_id, period)
    # balance отдельно: падение не откатывает счета
    if tenant_id:
        from app.services.counterparty_balance_service import (
            sync_counterparty_balances_safe,
        )

        sync_counterparty_balances_safe(tenant_id)
