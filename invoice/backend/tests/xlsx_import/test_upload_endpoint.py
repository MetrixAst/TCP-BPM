"""POST /api/xlsx-import/upload — self-serve xlsx upload for a TRC portal
login (the actual product flow: a mall's own staff uploads, see
resolve_tenant_id's auto-single-tenant resolution from the 2026-08-26
TRC-scope-leak fix, which this endpoint relies on for auth)."""
from unittest.mock import patch

import pytest

from app.core.security import create_trc_portal_token
from app.models.catalog import TRC, Tenant
from app.models.payment import TenantPayment
from app.models.tenant_data_file import TenantDataFile
from app.services.xlsx_import.parsers import maxi_mall

from .maxi_mall_fixture import COUNTERPARTY_CACHE_FIXTURE, build_workbook_bytes


@pytest.fixture(autouse=True)
def _fake_counterparty_cache():
    with patch(
        "app.services.xlsx_import.normalize._load_counterparty_cache_data",
        return_value=COUNTERPARTY_CACHE_FIXTURE,
    ), patch(
        "app.services.counterparty_cache_service.sync_xlsx_counterparty_directory",
        return_value=0,
    ):
        yield


def make_trc_tenant(db_session, *, xlsx_parser_key=maxi_mall.PARSER_KEY) -> tuple[TRC, Tenant]:
    trc = TRC(name="Maxi Mall Test", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Maxi Mall",
        legal_name="Maxi Mall LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        xlsx_parser_key=xlsx_parser_key,
        invoice_due_day=5,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def trc_headers(trc: TRC) -> dict:
    return {"Authorization": f"Bearer {create_trc_portal_token(trc.id)}"}


def _upload(client, trc, filename="report.xlsx", content=None):
    content = content if content is not None else build_workbook_bytes()
    return client.post(
        "/api/xlsx-import/upload",
        headers=trc_headers(trc),
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_successful_upload_returns_summary_and_writes_payments(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    response = _upload(client, trc)

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == tenant.id
    assert body["rows_total"] == 12
    assert body["rows_created"] == 12
    assert body["rows_matched"] == 10
    assert body["rows_unmatched"] == 2
    assert all(v["ok"] for v in body["totals_check"].values())

    rows = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).all()
    assert len(rows) == 12
    assert all(r.source == "xlsx" for r in rows)

    data_file = db_session.query(TenantDataFile).filter(TenantDataFile.tenant_id == tenant.id).first()
    assert data_file.status == "parsed_with_errors"  # has unmatched rows
    assert data_file.is_active is True


def test_reupload_creates_new_version_and_deactivates_old(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    _upload(client, trc, filename="v1.xlsx")
    _upload(client, trc, filename="v2.xlsx")

    files = db_session.query(TenantDataFile).filter(TenantDataFile.tenant_id == tenant.id).order_by(TenantDataFile.id).all()
    assert len(files) == 2
    assert files[0].is_active is False
    assert files[1].is_active is True
    assert files[1].original_filename == "v2.xlsx"

    # Re-upload must update the same 12 rows, not duplicate them.
    total_rows = db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).count()
    assert total_rows == 12


def test_rejects_non_xlsx_extension(client, db_session):
    trc, _tenant = make_trc_tenant(db_session)

    response = _upload(client, trc, filename="report.csv", content=b"a,b,c\n1,2,3")

    assert response.status_code == 400
    assert "xlsx" in response.json()["detail"].lower()


def test_rejects_empty_file(client, db_session):
    trc, _tenant = make_trc_tenant(db_session)

    response = _upload(client, trc, content=b"")

    assert response.status_code == 400


def test_tenant_without_parser_key_rejected(client, db_session):
    trc, _tenant = make_trc_tenant(db_session, xlsx_parser_key=None)

    response = _upload(client, trc)

    assert response.status_code == 400
    assert "не настроена" in response.json()["detail"]


def test_malformed_workbook_marks_file_failed(client, db_session):
    trc, tenant = make_trc_tenant(db_session)

    # Valid zip/xlsx container but missing the "Начисление"-prefixed sheets
    # entirely -> parse() returns zero rows/periods, not a raised error in
    # this parser (empty file, not malformed) — so instead send bytes that
    # aren't a valid xlsx at all, which openpyxl's load_workbook rejects.
    response = _upload(client, trc, content=b"not a real xlsx file")

    assert response.status_code == 422
    data_file = db_session.query(TenantDataFile).filter(TenantDataFile.tenant_id == tenant.id).first()
    assert data_file.status == "failed"
    assert data_file.error

    # Nothing should have been written to tenant_payments on a failed parse.
    assert db_session.query(TenantPayment).filter(TenantPayment.tenant_id == tenant.id).count() == 0


def test_requires_authentication(client, db_session):
    response = client.post(
        "/api/xlsx-import/upload",
        files={"file": ("report.xlsx", build_workbook_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 401
