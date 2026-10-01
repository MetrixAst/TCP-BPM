"""Shared fixtures for endpoint-level tests.

Uses an isolated in-memory SQLite DB per test — no real Postgres needed, so
these tests run the same on a laptop and in CI. TestClient is instantiated
without a `with` block on purpose: entering it as a context manager would
fire app.main's lifespan (starts the APScheduler), which is unrelated to
what these tests check and would reach for the real DATABASE_URL.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.catalog import TRC, Tenant, AdminUser, CounterpartyPhone
from app.models.notification import Notification
from app.models.payment import TenantPayment
from app.models.payment_sync_run import PaymentSyncRun
from app.models.tenant_data_file import TenantDataFile
from app.models.counterparty_balance import CounterpartyBalance
from app.models.invoice_pdf_payload import InvoicePdfPayload
from app.models.auto_notification_log import AutoNotificationLog

# Only the tables these tests actually touch: some other models (e.g.
# counterparty_cache) use Postgres-only column types (JSONB) that SQLite's
# compiler can't render, so a blanket Base.metadata.create_all() would fail.
# InvoicePdfPayload deliberately uses portable sa.JSON, not JSONB, exactly
# so it CAN be included here (see its model docstring).
_TEST_TABLES = [
    TRC.__table__,
    Tenant.__table__,
    PaymentSyncRun.__table__,
    TenantPayment.__table__,
    Notification.__table__,
    TenantDataFile.__table__,
    CounterpartyBalance.__table__,
    AdminUser.__table__,
    CounterpartyPhone.__table__,
    InvoicePdfPayload.__table__,
    AutoNotificationLog.__table__,
]


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine, tables=_TEST_TABLES)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
