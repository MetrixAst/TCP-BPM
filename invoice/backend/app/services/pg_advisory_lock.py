"""Postgres advisory locks — cheap mutual exclusion across process instances
with no extra infrastructure (no Redis/etcd/leader-election service needed).

Session-scoped: the lock is tied to a single DB connection and is released
automatically if that connection drops (crash, kill -9, pod eviction), unlike
most external lock services which need a TTL/heartbeat scheme to avoid a
stale lock surviving a crash. That property is exactly what's needed for
scheduler jobs — see app/scheduler.py (audit from 2026-08-25: the in-process
APScheduler runs in every uvicorn replica with no coordination, so scaling
past one replica means every replica sends the same hourly WhatsApp debtor
reminders and runs duplicate 1C syncs).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@contextmanager
def try_advisory_lock(engine: Engine, lock_key: int) -> Iterator[bool]:
    """Non-blocking: yields True if the lock was acquired (caller should do
    the work) or False if another process already holds it (caller should
    skip this run). Always releases on exit if it was acquired, and always
    closes its own dedicated connection — never borrows one from a caller's
    session, since the lock's lifetime must span exactly this `with` block.
    """
    conn = engine.connect()
    acquired = False
    try:
        acquired = bool(
            conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            except Exception:
                logger.exception("Failed to release advisory lock key=%s", lock_key)
        conn.close()
