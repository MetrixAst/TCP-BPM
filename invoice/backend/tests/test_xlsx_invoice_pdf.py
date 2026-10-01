"""app/services/xlsx_invoice_pdf.py — PDF generation for TenantPayment
rows imported from Excel (source="xlsx"). Built 2026-08-31 because none of
the existing 1C-download paths can ever serve these rows: they all require
a real 1C invoice_id and a live-or-cached 1C ownership check (_guid_literal,
assert_invoice_belongs_to_counterparty) that an xlsx row's synthetic
"xlsx:..." invoice_id fails by design (see normalize.py).

find_counterparty_in_cache() hits CounterpartyCache, a Postgres-only JSONB
table that SQLite's compiler can't render (see tests/conftest.py's own note
on this, and test_counterparty_directory_from_xlsx.py which only exercises
the pure compute_xlsx_counterparty_entries() for the same reason) — so it's
mocked in every test here rather than exercised against a real table."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.client_1c.exceptions import MissingSupplierRequisitesError
from app.models.payment import TenantPayment
from app.services.xlsx_invoice_pdf import (
    _line_item_name,
    _period_label,
    _service_label,
    assert_xlsx_payment_accessible,
    build_xlsx_invoice_payload,
    find_latest_xlsx_payment,
    render_xlsx_invoice_pdf,
)


def _xlsx_payment(**overrides) -> TenantPayment:
    defaults = dict(
        id=1,
        tenant_id=42,
        ip_name="ТОО Арендатор",
        tenant_name="ТОО Арендатор",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        status="unpaid",
        period="2026-08",
        amount=150000,
        counterparty_id="cp-1",
        service_type="rent",
        source="xlsx",
    )
    defaults.update(overrides)
    return TenantPayment(**defaults)


def _tenant():
    tenant = MagicMock()
    tenant.id = 42
    tenant.trc_id = 7
    tenant.legal_name = "ТОО Метрикс"
    tenant.name = "ТОО Метрикс"
    tenant.bin_value = "123456789012"
    tenant.invoice_iik = "KZ1234567890"
    tenant.invoice_kbe = "17"
    tenant.invoice_bank_name = "АО Банк"
    tenant.invoice_bank_bik = "BANKKZKA"
    tenant.invoice_payment_knp = "859"
    tenant.invoice_supplier_address = "г. Алматы"
    tenant.invoice_contract_text = "Без договора"
    return tenant


class TestPeriodAndServiceLabels:
    def test_period_label_formats_month_name(self):
        assert _period_label("2026-08") == "Август 2026"

    def test_period_label_falls_back_to_raw_on_bad_input(self):
        assert _period_label("garbage") == "garbage"

    def test_service_label_single_known_type(self):
        assert _service_label("rent") == "Аренда"

    def test_service_label_multiple_types_joined(self):
        assert _service_label("rent,utilities") == "Аренда + Коммунальные услуги"

    def test_service_label_unknown_type_falls_back_to_raw(self):
        assert _service_label("something_new") == "something_new"

    def test_service_label_empty_defaults_to_generic(self):
        assert _service_label(None) == "Услуги"
        assert _service_label("") == "Услуги"

    def test_line_item_name_combines_service_and_period_for_non_rent(self):
        payment = _xlsx_payment(service_type="utilities", period="2026-08")
        assert _line_item_name(payment) == "Коммунальные услуги за Август 2026"

    def test_line_item_name_omits_period_for_rent(self):
        """Real bug found 2026-09-03: rent is billed in advance for the
        NEXT month (a row from the "Начисление АВГУСТ" sheet bills
        September occupancy) — invoice_report.py's shared renderer already
        knows this and shifts+appends the month itself from
        payment.invoice_date (_item_name_with_payment_month, is_rent=True,
        month_offset=1). Baking "за Август 2026" in here ourselves made
        its own de-dup check think the (wrong) month was already present
        and skip the shift — so this must stay bare for rent, unlike every
        other service type."""
        payment = _xlsx_payment(service_type="rent", period="2026-08")
        assert _line_item_name(payment) == "Аренда"

    def test_line_item_name_rent_case_and_whitespace_insensitive(self):
        payment = _xlsx_payment(service_type=" RENT ", period="2026-08")
        assert _line_item_name(payment) == "Аренда"


class TestAssertXlsxPaymentAccessible:
    def test_missing_payment_raises_404(self):
        with pytest.raises(HTTPException) as exc_info:
            assert_xlsx_payment_accessible(None, tenant_id=42)
        assert exc_info.value.status_code == 404

    def test_non_xlsx_source_rejected(self):
        payment = _xlsx_payment(source="one_c")
        with pytest.raises(HTTPException) as exc_info:
            assert_xlsx_payment_accessible(payment, tenant_id=42)
        assert exc_info.value.status_code == 400

    def test_wrong_tenant_raises_403(self):
        payment = _xlsx_payment(tenant_id=42)
        with pytest.raises(HTTPException) as exc_info:
            assert_xlsx_payment_accessible(payment, tenant_id=99)
        assert exc_info.value.status_code == 403

    def test_matching_tenant_passes(self):
        payment = _xlsx_payment(tenant_id=42)
        assert assert_xlsx_payment_accessible(payment, tenant_id=42) is payment

    def test_admin_unrestricted_request_passes_regardless_of_tenant(self):
        """tenant_id=None is what scoped_tenant_id resolves to for an admin
        request with no tenant filter (see resolve_tenant_id) — same
        'unrestricted' meaning used everywhere else that dependency feeds
        into (PaymentService, get_1c_invoices, ...)."""
        payment = _xlsx_payment(tenant_id=42)
        assert assert_xlsx_payment_accessible(payment, tenant_id=None) is payment

    def test_unmatched_legacy_row_unreachable_by_locked_tenant(self):
        """tenant_id=None on the ROW (not the request) is the 'backfill
        couldn't match it' case documented on TenantPayment.tenant_id — a
        locked tenant/TRC login (any non-None resolved tenant_id) must not
        be able to reach it, only an unrestricted admin request can."""
        payment = _xlsx_payment(tenant_id=None)
        with pytest.raises(HTTPException) as exc_info:
            assert_xlsx_payment_accessible(payment, tenant_id=42)
        assert exc_info.value.status_code == 403


class TestBuildXlsxInvoicePayload:
    def test_payload_uses_counterparty_cache_name_and_bin_when_present(self):
        payment = _xlsx_payment()
        db = MagicMock()
        with patch(
            "app.services.xlsx_invoice_pdf.find_counterparty_in_cache",
            return_value={"id": "cp-1", "fullName": "Кэшированное Имя", "bin": "999888777666"},
        ):
            db.query.return_value.filter.return_value.first.return_value = None  # phone lookup
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["counterparty_name"] == "Кэшированное Имя"
        assert payload["counterparty_bin"] == "999888777666"

    def test_payload_falls_back_to_payment_row_name_without_cache_hit(self):
        payment = _xlsx_payment()
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["counterparty_name"] == "ТОО Арендатор"
        assert payload["counterparty_bin"] == ""

    def test_payload_number_date_amount_and_service_line(self):
        payment = _xlsx_payment(
            id=777,
            amount=250000,
            period="2026-09",
            invoice_date=date(2026, 9, 1),
            service_type="utilities",
        )
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["number"] == "777"
        assert payload["date"] == "2026-09-01"
        assert payload["amount"] == 250000.0
        assert payload["service_name"] == "Коммунальные услуги за Сентябрь 2026"
        assert payload["currency"] == "KZT"

    def test_supplier_requisites_merged_from_tenant(self):
        payment = _xlsx_payment()
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["supplier_name"] == "ТОО Метрикс"
        assert payload["supplier_bin"] == "123456789012"
        assert payload["supplier_iik"] == "KZ1234567890"
        assert payload["supplier_bik"] == "BANKKZKA"

    def test_rent_gets_knp_855(self):
        """Requested 2026-09-03 for Maxi Mall — automatic per-service-type
        КНП for xlsx invoices specifically (the 1C paths are untouched,
        still use tenant.invoice_payment_knp as one general value)."""
        payment = _xlsx_payment(service_type="rent")
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["payment_knp"] == "855"

    def test_utilities_gets_knp_856(self):
        payment = _xlsx_payment(service_type="utilities")
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["payment_knp"] == "856"

    def test_rent_knp_overrides_tenants_general_knp(self):
        """_tenant() fixture sets invoice_payment_knp="859" as the general
        fallback — rent/utilities must win over it, not the other way
        round (payload sets payment_knp before the merge, which only fills
        empty fields)."""
        payment = _xlsx_payment(service_type="rent")
        tenant = _tenant()
        assert tenant.invoice_payment_knp == "859"
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, tenant)

        assert payload["payment_knp"] == "855"

    def test_debt_falls_back_to_tenants_general_knp(self):
        """A charge type outside the rent/utilities map (debt, other,
        unknown) keeps the pre-existing behavior - tenant's own general
        KNP, same as the 1C paths always used."""
        payment = _xlsx_payment(service_type="debt")
        tenant = _tenant()
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, tenant)

        assert payload["payment_knp"] == "859"

    def test_rent_knp_case_and_whitespace_insensitive(self):
        payment = _xlsx_payment(service_type=" RENT ")
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["payment_knp"] == "855"

    def test_counterparty_phone_looked_up_by_trc_and_counterparty_id(self):
        payment = _xlsx_payment(counterparty_id="cp-42")
        db = MagicMock()
        phone_row = MagicMock(phone="+77001234567")
        db.query.return_value.filter.return_value.first.return_value = phone_row
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            payload = build_xlsx_invoice_payload(db, payment, _tenant())

        assert payload["counterparty_phone"] == "+77001234567"


class TestRenderXlsxInvoicePdf:
    def test_no_amount_raises_422(self):
        payment = _xlsx_payment(amount=None)
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            render_xlsx_invoice_pdf(db, payment, _tenant())
        assert exc_info.value.status_code == 422

    def test_tenant_without_bank_requisites_raises_missing_requisites_error(self):
        """Same rule the 1C download paths enforce
        (_pdf_payload_has_supplier_banks) — a PDF with no way to pay it is
        useless regardless of whether the data came from 1C or xlsx. Real
        case found 2026-08-31: a local xlsx-only test tenant that never had
        IIK/BIK entered at all."""
        payment = _xlsx_payment()
        db = MagicMock()
        tenant = _tenant()
        tenant.invoice_iik = None
        tenant.invoice_bank_bik = None
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None):
            db.query.return_value.filter.return_value.first.return_value = None
            with pytest.raises(MissingSupplierRequisitesError):
                render_xlsx_invoice_pdf(db, payment, tenant)

    def test_zero_amount_does_not_raise(self):
        """0 is a real (if unusual) amount, not 'missing data' — only None
        (the column's actual nullable-sentinel) should be rejected."""
        payment = _xlsx_payment(amount=0)
        db = MagicMock()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None), patch(
            "app.services.xlsx_invoice_pdf.generate_formal_invoice_document", return_value="/tmp/x.pdf"
        ) as mock_render:
            db.query.return_value.filter.return_value.first.return_value = None
            result = render_xlsx_invoice_pdf(db, payment, _tenant())

        assert result == "/tmp/x.pdf"
        mock_render.assert_called_once()

    def test_renders_via_shared_formal_invoice_layout(self):
        """Must go through the same renderer as real 1C invoices — not a
        separate/simplified layout — per the 2026-08-31 decision to make
        this indistinguishable in presentation from a real invoice."""
        payment = _xlsx_payment(invoice_id="xlsx:42:2026-08:cp-1:rent")
        db = MagicMock()
        tenant = _tenant()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None), patch(
            "app.services.xlsx_invoice_pdf.generate_formal_invoice_document", return_value="/tmp/x.pdf"
        ) as mock_render:
            db.query.return_value.filter.return_value.first.return_value = None
            render_xlsx_invoice_pdf(db, payment, tenant)

        args, _ = mock_render.call_args
        payload_arg, save_path_arg, tenant_arg = args
        assert payload_arg["number"] == "1"
        assert tenant_arg is tenant

    def test_save_path_keyed_by_invoice_id_not_pk(self):
        """The WhatsApp bulk-send worker (whatsapp_jobs._pdf_matches_invoice)
        checks that a pre-supplied file_path's filename contains the
        invoice_id before trusting it — keying by payment.id instead would
        silently discard every xlsx PDF attachment in that path and fall
        through to a live 1C re-fetch, which can never work for a synthetic
        "xlsx:..." id (found 2026-09-01 while wiring bulk send)."""
        payment = _xlsx_payment(invoice_id="xlsx:42:2026-08:cp-1:rent")
        db = MagicMock()
        tenant = _tenant()
        with patch("app.services.xlsx_invoice_pdf.find_counterparty_in_cache", return_value=None), patch(
            "app.services.xlsx_invoice_pdf.generate_formal_invoice_document", return_value="/tmp/x.pdf"
        ) as mock_render:
            db.query.return_value.filter.return_value.first.return_value = None
            render_xlsx_invoice_pdf(db, payment, tenant)

        _, save_path_arg, _ = mock_render.call_args[0]
        assert "xlsx_42_2026-08_cp-1_rent" in save_path_arg
        assert "xlsx-1" not in save_path_arg


_trc_counter = [0]


def _make_tenant_row(db_session):
    """Real DB rows, unlike _xlsx_payment()/_tenant() above — find_latest_
    xlsx_payment queries the actual tenant_payments table, no mocking a
    query builder makes sense for it (it's a real filter/order_by/first,
    not worth re-deriving by hand). TRC.name is unique, so a fresh name per
    call — this helper is used more than once per test."""
    from app.models.catalog import TRC, Tenant

    _trc_counter[0] += 1
    trc = TRC(name=f"Find Latest Xlsx Test TRC {_trc_counter[0]}", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Find Latest Xlsx Test Tenant",
        legal_name="Find Latest Xlsx Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _add_payment(db_session, tenant, **overrides):
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=f"xlsx:{tenant.id}:2026-08:cp-1:rent",
        ip_name="Арендатор",
        tenant_name="Арендатор",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        status="unpaid",
        period="2026-08",
        amount=100000,
        counterparty_id="cp-1",
        service_type="rent",
        source="xlsx",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


class TestFindLatestXlsxPayment:
    def test_returns_none_without_tenant_id(self, db_session):
        """Deliberate: unlike most tenant_id-optional lookups in this
        codebase (None usually means "admin, unrestricted"), this one must
        refuse outright — a virtual xlsx counterparty id is a hash of
        name+BIN, not guaranteed unique across tenants the way a real 1C
        GUID is, so an unscoped search could match the wrong tenant's row."""
        tenant = _make_tenant_row(db_session)
        _add_payment(db_session, tenant)

        assert find_latest_xlsx_payment(db_session, None, "cp-1") is None

    def test_returns_none_for_unknown_counterparty(self, db_session):
        tenant = _make_tenant_row(db_session)
        _add_payment(db_session, tenant)

        assert find_latest_xlsx_payment(db_session, tenant.id, "cp-does-not-exist") is None

    def test_ignores_non_xlsx_rows(self, db_session):
        tenant = _make_tenant_row(db_session)
        _add_payment(db_session, tenant, source="one_c", invoice_id="real-guid-1")

        assert find_latest_xlsx_payment(db_session, tenant.id, "cp-1") is None

    def test_scoped_to_tenant_even_with_same_counterparty_id(self, db_session):
        tenant_a = _make_tenant_row(db_session)
        tenant_b = _make_tenant_row(db_session)
        _add_payment(db_session, tenant_a, invoice_id="xlsx:a:2026-08:cp-1:rent")

        assert find_latest_xlsx_payment(db_session, tenant_b.id, "cp-1") is None

    def test_returns_most_recent_by_invoice_date(self, db_session):
        tenant = _make_tenant_row(db_session)
        _add_payment(
            db_session, tenant, invoice_id="xlsx:t:2026-06:cp-1:rent",
            invoice_date=date(2026, 6, 1), period="2026-06",
        )
        latest = _add_payment(
            db_session, tenant, invoice_id="xlsx:t:2026-08:cp-1:rent",
            invoice_date=date(2026, 8, 1), period="2026-08",
        )

        result = find_latest_xlsx_payment(db_session, tenant.id, "cp-1")

        assert result.id == latest.id

    def test_service_type_filters_by_substring_match(self, db_session):
        """service_type is comma-joined for multi-type charges
        ("rent,utilities") — must match a filter of just "rent", same
        convention payment_service.py's own filter already uses."""
        tenant = _make_tenant_row(db_session)
        _add_payment(
            db_session, tenant, invoice_id="xlsx:t:2026-08:cp-1:combo",
            service_type="rent,utilities",
        )

        result = find_latest_xlsx_payment(db_session, tenant.id, "cp-1", service_type="utilities")

        assert result is not None
        assert result.service_type == "rent,utilities"

    def test_service_type_excludes_non_matching(self, db_session):
        tenant = _make_tenant_row(db_session)
        _add_payment(db_session, tenant, service_type="utilities")

        result = find_latest_xlsx_payment(db_session, tenant.id, "cp-1", service_type="rent")

        assert result is None

    def test_counterparty_id_match_is_case_insensitive(self, db_session):
        tenant = _make_tenant_row(db_session)
        payment = _add_payment(db_session, tenant, counterparty_id="Virtual:AbC123")

        result = find_latest_xlsx_payment(db_session, tenant.id, "virtual:abc123")

        assert result.id == payment.id
