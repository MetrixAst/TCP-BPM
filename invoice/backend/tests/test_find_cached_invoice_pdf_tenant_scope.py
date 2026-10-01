"""find_cached_invoice_pdf used to look up a cached PDF purely by invoice_id,
in a single shared downloads/ directory — COM/Nova invoice ids aren't
guaranteed globally unique across 1C organizations, so a colliding invoice_id
could hand tenant B a PDF that was actually generated for tenant A (a
different counterparty's bank account/IIK/BIK, name, amounts). See audit from
2026-08-25.

When db+tenant_id are passed, the function now checks tenant_payments for
that invoice_id/tenant_id pair before returning a cached file."""

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.services.invoice_access import find_cached_invoice_pdf

_TEST_TABLES = [TRC.__table__, Tenant.__table__, TenantPayment.__table__]


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine, tables=_TEST_TABLES)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _write_cached_pdf(tmp_path, invoice_id: str):
    downloads = tmp_path / "downloads"
    downloads.mkdir(exist_ok=True)
    pdf_path = downloads / f"invoice_{invoice_id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    meta_path = downloads / f"invoice_{invoice_id}.pdf.meta.json"
    meta_path.write_text(json.dumps({"supplier_iik": "KZ123", "supplier_bik": "ABCDKZ"}))
    return pdf_path


def test_cached_pdf_hidden_when_invoice_belongs_to_different_tenant(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    trc = TRC(name="Test TRC")
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    owner = Tenant(
        trc_id=trc.id, name="Owner", legal_name="Owner LLP",
        one_c_login="", one_c_password="",
    )
    other = Tenant(
        trc_id=trc.id, name="Other", legal_name="Other LLP",
        one_c_login="", one_c_password="",
    )
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(other)

    db_session.add(
        TenantPayment(
            tenant_id=owner.id,
            ip_name=owner.legal_name,
            tenant_name="Some Counterparty",
            invoice_date=date(2026, 8, 1),
            due_date=date(2026, 8, 10),
            status=PaymentStatus.UNPAID,
            period="2026-08",
            invoice_id="INV-SHARED",
        )
    )
    db_session.commit()

    _write_cached_pdf(tmp_path, "INV-SHARED")

    # The tenant that actually owns this invoice sees the cached file.
    assert find_cached_invoice_pdf("INV-SHARED", db=db_session, tenant_id=owner.id)

    # A different tenant requesting the same (colliding) invoice_id must not.
    assert find_cached_invoice_pdf("INV-SHARED", db=db_session, tenant_id=other.id) is None


def test_cached_pdf_returned_without_tenant_scope_for_backward_compat(db_session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_cached_pdf(tmp_path, "INV-NOSCOPE")

    # No db/tenant_id passed -> old behavior (callers that don't have a
    # tenant context, e.g. none left in this codebase, but kept for safety).
    assert find_cached_invoice_pdf("INV-NOSCOPE") is not None
