from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services.counterparty_cache_service import (
    SYNC_RUNNING_STALE_MINUTES,
    clear_stale_counterparty_sync,
)


def test_clear_stale_counterparty_sync_resets_old_running():
    row = MagicMock()
    row.status = "running"
    row.started_at = datetime.now(timezone.utc) - timedelta(
        minutes=SYNC_RUNNING_STALE_MINUTES + 5
    )
    row.synced_at = datetime(2026, 6, 26, tzinfo=timezone.utc)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    assert clear_stale_counterparty_sync(db, tenant_id=3) is True
    assert row.status == "failed"
    assert "прервана" in (row.error or "").lower()
    db.commit.assert_called_once()


def test_clear_stale_counterparty_sync_keeps_recent_running():
    row = MagicMock()
    row.status = "running"
    row.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    assert clear_stale_counterparty_sync(db, tenant_id=3) is False
    db.commit.assert_not_called()
