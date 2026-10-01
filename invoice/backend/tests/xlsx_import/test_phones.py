"""sync_xlsx_counterparty_phones() — fills CounterpartyPhone from xlsx's
phone column (see parsers/avantage.py) only where there isn't one already,
so a fresh mock tenant can actually send/test WhatsApp without retyping
every number by hand into the admin panel."""
from datetime import date

import pytest

from app.models.catalog import TRC, CounterpartyPhone, Tenant
from app.models.payment import PaymentStatus
from app.services.xlsx_import.phones import compute_phone_upserts, sync_xlsx_counterparty_phones
from app.services.xlsx_import.types import NormalizedRow, RawChargeRow


def make_tenant(db_session) -> Tenant:
    trc = TRC(name="Phones Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id, name="Phones Test Tenant", legal_name="Phones Test Tenant LLP",
        one_c_login="", one_c_password="", is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _raw(name="Renter", phone=None) -> RawChargeRow:
    return RawChargeRow(
        raw_name=name, period="2026-08", charge_type="rent",
        charged=100000, paid=0, remainder=100000, phone=phone,
    )


def _normalized(*, cp_id, ip_name, phone=None, service_type="rent") -> NormalizedRow:
    return NormalizedRow(
        tenant_id=1,
        invoice_id=f"xlsx:1:2026-08:{cp_id}:{service_type}",
        counterparty_id=cp_id,
        ip_name=ip_name,
        tenant_name=ip_name,
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 5),
        period="2026-08",
        service_type=service_type,
        amount=100000,
        paid_amount=0,
        status=PaymentStatus.UNPAID.value,
        matched=False,
        source_row=_raw(ip_name, phone),
    )


class TestComputePhoneUpserts:
    def test_row_without_phone_produces_nothing(self):
        rows = [_normalized(cp_id="virtual:aaa", ip_name="No Phone TOO", phone=None)]
        assert compute_phone_upserts(rows) == {}

    def test_row_with_phone_included(self):
        rows = [_normalized(cp_id="virtual:aaa", ip_name="Has Phone TOO", phone="77475424201")]
        entries = compute_phone_upserts(rows)
        assert entries == {"virtual:aaa": {"phone": "77475424201", "counterparty_name": "Has Phone TOO"}}

    def test_first_nonempty_phone_wins_across_service_types(self):
        rows = [
            _normalized(cp_id="virtual:aaa", ip_name="Renter", phone=None, service_type="rent"),
            _normalized(cp_id="virtual:aaa", ip_name="Renter", phone="77475424201", service_type="debt"),
        ]
        entries = compute_phone_upserts(rows)
        assert entries["virtual:aaa"]["phone"] == "77475424201"


class TestSyncXlsxCounterpartyPhones:
    def test_creates_phone_row_when_none_exists(self, db_session):
        tenant = make_tenant(db_session)
        rows = [_normalized(cp_id="virtual:aaa", ip_name="New Tenant TOO", phone="77475424201")]

        created = sync_xlsx_counterparty_phones(db_session, tenant, rows)

        assert created == 1
        row = (
            db_session.query(CounterpartyPhone)
            .filter(CounterpartyPhone.trc_id == tenant.trc_id, CounterpartyPhone.one_c_counterparty_id == "virtual:aaa")
            .first()
        )
        assert row is not None
        assert row.phone == "77475424201"

    def test_does_not_overwrite_existing_phone(self, db_session):
        """The core invariant this whole module exists to respect — an
        admin-entered (or previously xlsx-filled) phone is never
        auto-overwritten, same rule CounterpartyPhone already applies to
        1C's own phone hint (see app/api/admin.py counterparty_directory)."""
        tenant = make_tenant(db_session)
        db_session.add(
            CounterpartyPhone(
                trc_id=tenant.trc_id,
                one_c_counterparty_id="virtual:aaa",
                counterparty_name="Old Name",
                phone="70000000000",
            )
        )
        db_session.commit()

        rows = [_normalized(cp_id="virtual:aaa", ip_name="New Name TOO", phone="77475424201")]
        created = sync_xlsx_counterparty_phones(db_session, tenant, rows)

        assert created == 0
        row = (
            db_session.query(CounterpartyPhone)
            .filter(CounterpartyPhone.trc_id == tenant.trc_id, CounterpartyPhone.one_c_counterparty_id == "virtual:aaa")
            .first()
        )
        assert row.phone == "70000000000"
        assert row.counterparty_name == "Old Name"

    def test_no_rows_with_phone_is_a_noop(self, db_session):
        tenant = make_tenant(db_session)
        rows = [_normalized(cp_id="virtual:aaa", ip_name="No Phone TOO", phone=None)]

        created = sync_xlsx_counterparty_phones(db_session, tenant, rows)

        assert created == 0
        assert db_session.query(CounterpartyPhone).count() == 0

    def test_tenant_without_trc_id_is_a_noop(self, db_session):
        tenant = make_tenant(db_session)
        tenant.trc_id = None
        rows = [_normalized(cp_id="virtual:aaa", ip_name="Has Phone TOO", phone="77475424201")]

        created = sync_xlsx_counterparty_phones(db_session, tenant, rows)

        assert created == 0
