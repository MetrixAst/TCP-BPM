"""app/services/xlsx_bulk_notify_service.py — bulk WhatsApp send for
xlsx-imported invoices, built 2026-09-01 for Maxi Mall's ~150-tenant
September rent run. Deliberately a separate module/table-scope from
bulk_debtor_notify_service.py (see that module's own docstring) — these
tests exist partly to prove that separation: nothing here should ever
touch a live 1C client, and the pure-1C bulk path's own tests
(test_bulk_debtor_notify_service_type_filter.py) must keep passing
unmodified alongside these.

find_counterparty_in_cache() hits CounterpartyCache (Postgres-only JSONB,
see tests/conftest.py's own note) — mocked in every test that reaches it,
same pattern as test_xlsx_invoice_pdf.py."""
from datetime import date
from unittest.mock import patch

import pytest

from app.models.catalog import TRC, CounterpartyPhone, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.models.auto_notification_log import AutoNotificationLog
from app.services.xlsx_bulk_notify_service import (
    count_xlsx_invoice_candidates,
    preview_xlsx_invoice_notifications,
    queue_xlsx_invoice_notifications,
)

_trc_counter = [0]


def make_tenant(db_session, **overrides) -> Tenant:
    _trc_counter[0] += 1
    trc = TRC(name=f"Xlsx Bulk Test TRC {_trc_counter[0]}", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    defaults = dict(
        trc_id=trc.id,
        name="Xlsx Bulk Test Tenant",
        legal_name="Xlsx Bulk Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
        invoice_iik="KZ999CURRENTACCOUNT",
        invoice_bank_bik="CURRENTBIK",
        invoice_bank_name="Current Bank",
        invoice_kbe="17",
    )
    defaults.update(overrides)
    tenant = Tenant(**defaults)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


_payment_counter = [0]


def make_payment(db_session, tenant: Tenant, **overrides) -> TenantPayment:
    _payment_counter[0] += 1
    n = _payment_counter[0]
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=f"xlsx:{tenant.id}:2026-09:cp-{n}:rent",
        ip_name=f"Арендатор {n}",
        tenant_name=f"Арендатор {n}",
        invoice_date=date(2026, 9, 1),
        due_date=date(2026, 9, 15),
        status=PaymentStatus.UNPAID,
        period="2026-09",
        amount=100000,
        counterparty_id=f"cp-{n}",
        service_type="rent",
        source="xlsx",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    # Two references to patch: xlsx_bulk_notify_service's own direct call,
    # and xlsx_invoice_pdf.build_xlsx_invoice_payload's separate import of
    # the same function (reached by preview_xlsx_invoice_notifications'
    # missing-requisites check) — CounterpartyCache is Postgres-only JSONB,
    # unrenderable on this in-memory SQLite test DB either way.
    with patch(
        "app.services.xlsx_bulk_notify_service.find_counterparty_in_cache",
        return_value=None,
    ), patch(
        "app.services.xlsx_invoice_pdf.find_counterparty_in_cache",
        return_value=None,
    ):
        yield


@pytest.fixture(autouse=True)
def _no_pdf_render():
    with patch(
        "app.services.xlsx_bulk_notify_service.render_xlsx_invoice_pdf",
        return_value="/tmp/fake-invoice.pdf",
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_send():
    """send_notification would otherwise try a real deliver_notification
    (Green API HTTP call) since KAFKA_ENABLED defaults False in tests."""
    with patch(
        "app.services.notification_service.NotificationService.send_notification",
        return_value=(None, True),
    ) as mock_send:
        yield mock_send


def _add_phone(db_session, tenant: Tenant, counterparty_id: str, phone: str) -> None:
    db_session.add(
        CounterpartyPhone(trc_id=tenant.trc_id, one_c_counterparty_id=counterparty_id, phone=phone)
    )
    db_session.commit()


class TestCountXlsxInvoiceCandidates:
    def test_counts_matching_rows(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant)
        make_payment(db_session, tenant)

        assert count_xlsx_invoice_candidates(db_session, tenant_id=tenant.id, period="2026-09") == 2

    def test_excludes_zero_and_none_amount(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, amount=0)
        make_payment(db_session, tenant, amount=None)
        make_payment(db_session, tenant, amount=5000)

        assert count_xlsx_invoice_candidates(db_session, tenant_id=tenant.id, period="2026-09") == 1

    def test_excludes_other_periods_and_tenants(self, db_session):
        tenant_a = make_tenant(db_session)
        tenant_b = make_tenant(db_session)
        make_payment(db_session, tenant_a, period="2026-08")
        make_payment(db_session, tenant_a, period="2026-09")
        make_payment(db_session, tenant_b, period="2026-09")

        assert count_xlsx_invoice_candidates(db_session, tenant_id=tenant_a.id, period="2026-09") == 1

    def test_excludes_non_xlsx_rows(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, source="one_c", invoice_id="real-guid-1")

        assert count_xlsx_invoice_candidates(db_session, tenant_id=tenant.id, period="2026-09") == 0

    def test_service_type_filter(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant, service_type="rent")
        make_payment(db_session, tenant, service_type="utilities", invoice_id=f"xlsx:{tenant.id}:2026-09:cp-x:utilities", counterparty_id="cp-x")

        assert count_xlsx_invoice_candidates(
            db_session, tenant_id=tenant.id, period="2026-09", service_type="rent"
        ) == 1


class TestQueueXlsxInvoiceNotifications:
    def test_unknown_tenant_returns_error_dict(self, db_session):
        result = queue_xlsx_invoice_notifications(db_session, tenant_id=999999, period="2026-09")
        assert result["errors"] == 1
        assert result["queued"] == 0

    def test_happy_path_queues_and_renders(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["queued"] == 1
        assert result["errors"] == 0
        assert result["skipped_no_phone"] == 0

    def test_no_phone_is_skipped_not_error(self, db_session):
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant)  # no CounterpartyPhone row, cache mocked to None too

        result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_no_phone"] == 1
        assert result["queued"] == 0

    def test_zero_amount_skipped_not_sent(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant, amount=0)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_no_amount"] == 1
        assert result["queued"] == 0

    def test_missing_supplier_requisites_counted_separately(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        from app.client_1c.exceptions import MissingSupplierRequisitesError

        with patch(
            "app.services.xlsx_bulk_notify_service.render_xlsx_invoice_pdf",
            side_effect=MissingSupplierRequisitesError("нет IIK/BIK"),
        ):
            result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_missing_requisites"] == 1
        assert result["queued"] == 0

    def test_second_run_same_day_is_deduplicated(self, db_session):
        """The idempotency guarantee — a re-run (retry, or an operator
        clicking the button twice) must not double-send."""
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        first = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")
        second = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert first["queued"] == 1
        assert second["queued"] == 0
        assert second["skipped_duplicate"] == 1

    def test_force_bypasses_duplicate_guard(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")
        second = queue_xlsx_invoice_notifications(
            db_session, tenant_id=tenant.id, period="2026-09", force=True
        )

        assert second["queued"] == 1
        assert second["skipped_duplicate"] == 0

    def test_does_not_send_other_tenants_rows(self, db_session):
        tenant_a = make_tenant(db_session)
        tenant_b = make_tenant(db_session)
        payment_a = make_payment(db_session, tenant_a)
        make_payment(db_session, tenant_b)
        _add_phone(db_session, tenant_a, payment_a.counterparty_id, "+77001234567")

        result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant_a.id, period="2026-09")

        assert result["candidates"] == 1
        assert result["queued"] == 1

    def test_does_not_send_other_periods(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant, period="2026-08", invoice_id=f"xlsx:{tenant.id}:2026-08:cp-1:rent")
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["candidates"] == 0
        assert result["queued"] == 0

    def test_service_type_filter_narrows_the_batch(self, db_session):
        tenant = make_tenant(db_session)
        rent = make_payment(db_session, tenant, service_type="rent")
        util = make_payment(
            db_session, tenant, service_type="utilities",
            invoice_id=f"xlsx:{tenant.id}:2026-09:cp-x:utilities", counterparty_id="cp-x",
        )
        _add_phone(db_session, tenant, rent.counterparty_id, "+77001111111")
        _add_phone(db_session, tenant, util.counterparty_id, "+77002222222")

        result = queue_xlsx_invoice_notifications(
            db_session, tenant_id=tenant.id, period="2026-09", service_type="rent"
        )

        assert result["candidates"] == 1
        assert result["queued"] == 1

    def test_counterparty_id_filter_narrows_to_one(self, db_session):
        tenant = make_tenant(db_session)
        p1 = make_payment(db_session, tenant)
        p2 = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, p1.counterparty_id, "+77001111111")
        _add_phone(db_session, tenant, p2.counterparty_id, "+77002222222")

        result = queue_xlsx_invoice_notifications(
            db_session, tenant_id=tenant.id, period="2026-09", counterparty_id=p1.counterparty_id
        )

        assert result["candidates"] == 1
        assert result["queued"] == 1

    def test_one_bad_row_does_not_stop_the_batch(self, db_session):
        """A render failure on row N must not prevent rows N+1..M from
        being sent — 150 rows, one bad apple, should not zero out the run."""
        tenant = make_tenant(db_session)
        bad = make_payment(db_session, tenant)
        good = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, bad.counterparty_id, "+77001111111")
        _add_phone(db_session, tenant, good.counterparty_id, "+77002222222")

        def render_side_effect(db, payment, tenant):
            if payment.id == bad.id:
                raise RuntimeError("boom")
            return "/tmp/fake-invoice.pdf"

        with patch(
            "app.services.xlsx_bulk_notify_service.render_xlsx_invoice_pdf",
            side_effect=render_side_effect,
        ):
            result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["errors"] == 1
        assert result["queued"] == 1


class TestPreviewXlsxInvoiceNotifications:
    """Dry run — must have ZERO side effects (no AutoNotificationLog row,
    no Notification, no PDF render, no send) while reporting exactly what
    queue_xlsx_invoice_notifications would do, so a real send right after
    a preview sees the same candidates rather than "already sent"."""

    def test_unknown_tenant_returns_error_dict(self, db_session):
        result = preview_xlsx_invoice_notifications(db_session, tenant_id=999999, period="2026-09")
        assert result["candidates"] == 0
        assert result["would_queue"] == 0

    def test_happy_path_reports_would_queue(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        result = preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["would_queue"] == 1
        assert result["skipped_rows"] == []

    def test_never_writes_a_send_slot(self, db_session):
        """The critical guarantee: preview must not consume today's
        idempotency slot, or the real send afterward would skip every row
        as "already sent" without ever actually sending anything."""
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert db_session.query(AutoNotificationLog).count() == 0

        # The real send right after must still queue it for real.
        result = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")
        assert result["queued"] == 1
        assert result["skipped_duplicate"] == 0

    def test_never_sends_or_renders(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        with patch(
            "app.services.xlsx_bulk_notify_service.render_xlsx_invoice_pdf",
            side_effect=AssertionError("preview must never render a PDF"),
        ):
            preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

    def test_reports_no_phone_row_with_details(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)

        result = preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_no_phone"] == 1
        assert result["skipped_rows"][0]["reason"] == "no_phone"
        assert result["skipped_rows"][0]["counterparty_id"] == payment.counterparty_id
        assert result["skipped_rows"][0]["amount"] == 100000.0

    def test_reports_no_amount_row(self, db_session):
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant, amount=0)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        result = preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_no_amount"] == 1
        assert result["skipped_rows"][0]["reason"] == "no_amount"

    def test_reports_missing_requisites_row(self, db_session):
        tenant = make_tenant(
            db_session, invoice_iik=None, invoice_bank_bik=None, invoice_bank_name=None, invoice_kbe=None
        )
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        result = preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_missing_requisites"] == 1
        assert result["skipped_rows"][0]["reason"] == "missing_requisites"
        assert result["would_queue"] == 0

    def test_reports_duplicate_without_consuming_it_twice(self, db_session):
        """A second preview after a real send correctly reports duplicate
        (matches what a real second send would do) without writing
        anything new itself."""
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        _add_phone(db_session, tenant, payment.counterparty_id, "+77001234567")

        queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")
        result = preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert result["skipped_duplicate"] == 1
        assert result["would_queue"] == 0
        assert db_session.query(AutoNotificationLog).count() == 1  # not 2

    def test_agrees_with_queue_on_candidate_count(self, db_session):
        """The two functions must never quietly disagree on scope — they
        share _matching_payments_query for exactly this reason."""
        tenant = make_tenant(db_session)
        make_payment(db_session, tenant)
        make_payment(db_session, tenant, amount=0)

        preview = preview_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")
        real = queue_xlsx_invoice_notifications(db_session, tenant_id=tenant.id, period="2026-09")

        assert preview["candidates"] == real["candidates"] == 2
