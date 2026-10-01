
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.payment_sync_run import PaymentSyncRun


def _tenant_key(tenant_id: Optional[int]) -> int:
    return int(tenant_id) if tenant_id is not None else 0


def _row_to_dict(row: PaymentSyncRun) -> dict[str, Any]:
    return {
        "status": row.status,
        "period": row.period,
        "tenant_id": row.tenant_id or None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error": row.error,
        "records": row.records,
    }


def get_status(db: Session, tenant_id: Optional[int], period: str) -> Optional[dict[str, Any]]:
    row = (
        db.query(PaymentSyncRun)
        .filter(
            PaymentSyncRun.tenant_id == _tenant_key(tenant_id),
            PaymentSyncRun.period == period,
        )
        .first()
    )
    if not row:
        return None
    return _row_to_dict(row)


def set_running(db: Session, tenant_id: Optional[int], period: str) -> bool:
    """Возвращает False, если синхронизация уже идёт."""
    key = _tenant_key(tenant_id)
    row = (
        db.query(PaymentSyncRun)
        .filter(PaymentSyncRun.tenant_id == key, PaymentSyncRun.period == period)
        .first()
    )
    if row and row.status == "running":
        return False
    now = datetime.now(timezone.utc)
    if row:
        row.status = "running"
        row.started_at = now
        row.finished_at = None
        row.error = None
        row.records = None
    else:
        db.add(
            PaymentSyncRun(
                tenant_id=key,
                period=period,
                status="running",
                started_at=now,
            )
        )
    db.commit()
    return True


def set_done(db: Session, tenant_id: Optional[int], period: str, records: int) -> None:
    key = _tenant_key(tenant_id)
    row = (
        db.query(PaymentSyncRun)
        .filter(PaymentSyncRun.tenant_id == key, PaymentSyncRun.period == period)
        .first()
    )
    now = datetime.now(timezone.utc)
    if row:
        row.status = "done"
        row.finished_at = now
        row.error = None
        row.records = records
    else:
        db.add(
            PaymentSyncRun(
                tenant_id=key,
                period=period,
                status="done",
                started_at=now,
                finished_at=now,
                records=records,
            )
        )
    db.commit()


def set_failed(db: Session, tenant_id: Optional[int], period: str, error: str) -> None:
    key = _tenant_key(tenant_id)
    row = (
        db.query(PaymentSyncRun)
        .filter(PaymentSyncRun.tenant_id == key, PaymentSyncRun.period == period)
        .first()
    )
    now = datetime.now(timezone.utc)
    if row:
        row.status = "failed"
        row.finished_at = now
        row.error = error
    else:
        db.add(
            PaymentSyncRun(
                tenant_id=key,
                period=period,
                status="failed",
                started_at=now,
                finished_at=now,
                error=error,
            )
        )
    db.commit()
