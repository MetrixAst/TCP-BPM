"""Real bug found 2026-09-14 (Astranium/"Toys market" invoice №00000003340)
while fixing invoice_pdf_cache's line-item TTL (LINE_ITEMS_FRESHNESS_TTL,
see test_invoice_pdf_cache.py::TestLineItemsFreshnessTtl): the payload-level
TTL alone is not enough for the Nova client. Every payload-cache-hit render
(NovaBuh1CClient.download_invoice_file's cached_payload branch) writes fresh
bytes to the SAME on-disk path that the separate file-level PDF cache
(_try_reuse_cached_pdf, _PDF_CACHE_MAX_AGE=7 days) checks by mtime — so that
file's mtime is perpetually "just rendered", never ages out on its own, and
would silently serve the exact same stale content again even after the
payload cache itself has expired, without ever reaching live 1C. Fixed by
having download_invoice_file also invalidate the on-disk file (and its
.meta.json) whenever invoice_pdf_cache.is_payload_cache_stale() says the
payload cache expired specifically (not just "was never cached", which must
NOT touch the file cache — see the complementary test below)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, Tenant
from app.models.invoice_pdf_payload import InvoicePdfPayload
from app.services.invoice_pdf_cache import LINE_ITEMS_FRESHNESS_TTL, store_payload_if_valid
from app.services.nova_1c_service import Nova1CServiceError
from app.services.nova_buh_1c_client import NovaBuh1CClient

_REAL_INVOICE_ID = "f49e3940-9563-11f1-b522-4c526260eadb"
_REAL_CP_ID = "f49e393a-9563-11f1-b522-4c526260eadb"


def _valid_payload(**overrides) -> dict:
    payload = {
        "id": _REAL_INVOICE_ID,
        "number": "18490",
        "date": "2026-08-01",
        "counterparty_id": _REAL_CP_ID,
        "counterparty_name": "Тестовый Арендатор ТОО",
        "amount": 500000,
        "currency": "KZT",
        "items": [{"name": "Аренда за август", "quantity": 1, "price": 500000, "amount": 500000}],
    }
    payload.update(overrides)
    return payload


def make_tenant(db_session) -> Tenant:
    trc = TRC(name="Nova Stale-File Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Nova Stale-File Test Tenant",
        legal_name="Nova Stale-File Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        invoice_iik="KZ999CURRENTACCOUNT",
        invoice_bank_bik="CURRENTBIK",
        invoice_bank_name="Current Bank",
        invoice_kbe="17",
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _neutered_client() -> NovaBuh1CClient:
    """A client whose entire live-1C cascade is short-circuited to produce
    nothing, so download_invoice_file falls straight through to its final
    'could not get a PDF' error — without ever touching a network. Only the
    caching decision at the top of the method (what this test targets) can
    have any observable effect before that point."""
    from unittest.mock import MagicMock

    client = NovaBuh1CClient(organization_id=1, service=MagicMock())
    client._ensure_agent_id = lambda: None  # self._agent_id stays None -> getpdf branch skipped
    client._ensure_scripts = lambda: None  # self._script_ids stays {} -> script_keys == []
    client._lookup_batch_invoice = lambda invoice_id: (None, [])
    return client


class TestStaleCacheInvalidatesTheFileCacheToo:
    def test_stale_payload_cache_deletes_the_shadowing_pdf_file(self, db_session, tmp_path):
        """The actual fix: without it, this test's pre-seeded PDF file would
        still be sitting at `save_path` with a fresh mtime and would get
        served by _try_reuse_cached_pdf, so the (mocked-empty) live cascade
        below would never even run — the bug this test guards against."""
        tenant = make_tenant(db_session)
        store_payload_if_valid(
            db_session, tenant.id, _REAL_INVOICE_ID, _valid_payload(), source="nova", tenant=tenant
        )
        row = db_session.query(InvoicePdfPayload).filter(
            InvoicePdfPayload.tenant_id == tenant.id, InvoicePdfPayload.invoice_id == _REAL_INVOICE_ID
        ).first()
        row.fetched_at = datetime.now(timezone.utc) - LINE_ITEMS_FRESHNESS_TTL - timedelta(minutes=1)
        db_session.commit()

        # Must actually pass _try_reuse_cached_pdf's own gates (real minimum
        # size, matching layout version, bank data in the sidecar meta) —
        # otherwise this test would pass/fail independent of the fix being
        # tested, by tripping over an unrelated gate instead.
        from app.services.nova_buh_1c_client import _PDF_LAYOUT_VERSION

        save_path = tmp_path / "invoice.pdf"
        save_path.write_bytes(b"%PDF-1.4 " + b"stale rendered bytes from the last cache-hit view " * 20)
        meta_path = tmp_path / "invoice.pdf.meta.json"
        meta_path.write_text(
            f'{{"layout_version": {_PDF_LAYOUT_VERSION}, "supplier_iik": "X", "supplier_bik": "Y"}}'
        )

        client = _neutered_client()
        # download_invoice_file opens its own app.db.database.SessionLocal()
        # for the cache check (not the request-scoped session it was given
        # any tenant through) — route that to this test's in-memory session,
        # same pattern as test_bulk_debtor_notify_service_type_filter.py.
        with patch("app.db.database.SessionLocal", return_value=db_session):
            with pytest.raises(Nova1CServiceError):
                client.download_invoice_file(_REAL_INVOICE_ID, save_path=str(save_path), tenant=tenant)

        assert not save_path.exists(), "stale PDF must be invalidated, not silently re-served"
        assert not meta_path.exists()

    def test_never_cached_invoice_does_not_touch_an_existing_file_cache_hit(self, db_session, tmp_path):
        """Complementary guard: when there's simply no payload cache row at
        all (not the 'expired' case), the pre-existing file-level PDF cache
        must keep working exactly as before — this fix must not regress
        that unrelated, already-correct behavior."""
        tenant = make_tenant(db_session)

        save_path = tmp_path / "invoice.pdf"
        # Must look like a real, fresh, layout-compatible cached PDF to
        # _try_reuse_cached_pdf (see nova_buh_1c_client._cached_pdf_layout_ok
        # / _PDF_LAYOUT_VERSION) for it to actually be served.
        from app.services.nova_buh_1c_client import _PDF_LAYOUT_VERSION

        save_path.write_bytes(b"%PDF-1.4 " + b"x" * 500)
        meta_path = tmp_path / "invoice.pdf.meta.json"
        meta_path.write_text(
            f'{{"layout_version": {_PDF_LAYOUT_VERSION}, "supplier_iik": "X", "supplier_bik": "Y"}}'
        )

        client = _neutered_client()
        with patch("app.db.database.SessionLocal", return_value=db_session):
            result = client.download_invoice_file(_REAL_INVOICE_ID, save_path=str(save_path), tenant=tenant)

        assert result == str(save_path.resolve())
        assert save_path.exists()
