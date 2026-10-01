"""app/scheduler.py used to have no coordination at all across process
instances — it's an in-process APScheduler started in every uvicorn replica's
lifespan. The moment this API scales past one replica, every replica
independently sends the same hourly WhatsApp debtor reminders (customer-
facing duplicate messages) and runs duplicate 1C syncs. See audit from
2026-08-25.

pg_advisory_lock is genuinely Postgres-only (CI has no real Postgres — see
.gitlab-ci.yml, DATABASE_URL there is a placeholder never actually connected
to), so these tests mock the DB layer rather than hitting a real database;
the lock SQL itself was verified manually against the local dev Postgres.
"""
from unittest.mock import MagicMock, patch

from app.services.pg_advisory_lock import try_advisory_lock


def _mock_engine(lock_result: bool):
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = lock_result
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine, conn


class TestTryAdvisoryLock:
    def test_yields_true_and_unlocks_on_exit_when_acquired(self):
        engine, conn = _mock_engine(lock_result=True)
        with try_advisory_lock(engine, 42) as acquired:
            assert acquired is True
        # pg_try_advisory_lock then pg_advisory_unlock, same key.
        calls = conn.execute.call_args_list
        assert "pg_try_advisory_lock" in str(calls[0].args[0])
        assert "pg_advisory_unlock" in str(calls[1].args[0])
        conn.close.assert_called_once()

    def test_yields_false_and_does_not_unlock_when_not_acquired(self):
        engine, conn = _mock_engine(lock_result=False)
        with try_advisory_lock(engine, 42) as acquired:
            assert acquired is False
        # Only the try-lock call — never call unlock for a lock we don't hold.
        assert conn.execute.call_count == 1
        conn.close.assert_called_once()

    def test_connection_closed_and_unlocked_even_if_body_raises(self):
        engine, conn = _mock_engine(lock_result=True)
        try:
            with try_advisory_lock(engine, 42) as acquired:
                assert acquired is True
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert conn.execute.call_count == 2  # try_lock + unlock
        conn.close.assert_called_once()

    def test_unlock_failure_does_not_propagate(self):
        engine, conn = _mock_engine(lock_result=True)

        def side_effect(*args, **kwargs):
            sql = str(args[0])
            if "pg_advisory_unlock" in sql:
                raise RuntimeError("connection lost")
            result = MagicMock()
            result.scalar.return_value = True
            return result

        conn.execute.side_effect = side_effect
        with try_advisory_lock(engine, 42) as acquired:
            assert acquired is True
        conn.close.assert_called_once()


class TestSchedulerJobsSkipWhenLockHeldElsewhere:
    def test_auto_invoice_notifications_skips_when_lock_not_acquired(self):
        from app.scheduler import run_auto_invoice_notifications

        with patch("app.scheduler.try_advisory_lock") as lock_cm, patch(
            "app.services.auto_notification_service.AutoNotificationService"
        ) as Service:
            lock_cm.return_value.__enter__.return_value = False
            run_auto_invoice_notifications()
        Service.assert_not_called()

    def test_hourly_tenant_data_sync_skips_when_lock_not_acquired(self):
        from app.scheduler import run_hourly_tenant_data_sync

        with patch("app.scheduler.try_advisory_lock") as lock_cm, patch(
            "app.services.counterparty_cache_service.schedule_all_active_tenants_sync"
        ) as schedule_fn:
            lock_cm.return_value.__enter__.return_value = False
            run_hourly_tenant_data_sync()
        schedule_fn.assert_not_called()

    def test_auto_invoice_notifications_runs_when_lock_acquired(self):
        from app.scheduler import run_auto_invoice_notifications

        with patch("app.scheduler.try_advisory_lock") as lock_cm, patch(
            "app.services.auto_notification_service.AutoNotificationService"
        ) as Service:
            lock_cm.return_value.__enter__.return_value = True
            Service.return_value.run_for_all_tenants.return_value = 0
            run_auto_invoice_notifications()
        Service.return_value.run_for_all_tenants.assert_called_once()
