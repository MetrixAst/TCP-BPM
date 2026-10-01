"""build_whatsapp_message — real gap found 2026-09-02 (reported directly
against a real manual send to Maxi Mall): the WhatsApp message text showed
the invoice's raw period ("Период: 2026-09") for a RENT charge, while the
PDF for the exact same invoice already shows the +1-shifted month ("за
Октябрь", fixed the same day in invoice_report.py — rent is billed in
advance for next month). This text path never got that fix, and Maxi
Mall's own custom message_template hardcoded a literal "за Август" since
there was never a dynamic month placeholder to use instead.

Also covers: the falsely-labeled amount/period text should reflect the
SAME advance-billing split as the PDF — rent always shifts, operations
only for tenants with invoice_operations_advance_billing=True, everything
else stays "по факту"."""
from datetime import date
from unittest.mock import MagicMock, patch

from app.models.payment import PaymentStatus
from app.services.message_builder import (
    _display_period,
    _period_month_name,
    _shift_period,
    build_whatsapp_message,
)


def _payment(**overrides):
    p = MagicMock()
    p.period = "2026-09"
    p.amount = 597168
    p.due_date = date(2026, 9, 15)
    p.tenant_name = "Admix Sport"
    p.invoice_id = "a57d2d95-8675-11f1-b51e-4c526260eadc"
    p.status = PaymentStatus.UNPAID
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def _tenant(**overrides):
    t = MagicMock()
    t.invoice_operations_advance_billing = False
    t.message_template = None
    t.name = "Maxi Mall"
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


class TestShiftPeriod:
    def test_shifts_forward_one_month(self):
        assert _shift_period("2026-09", 1) == "2026-10"

    def test_wraps_year_boundary(self):
        assert _shift_period("2026-12", 1) == "2027-01"

    def test_unparseable_input_returned_unchanged(self):
        assert _shift_period("not-a-period", 1) == "not-a-period"


class TestPeriodMonthName:
    def test_returns_russian_month_and_year(self):
        assert _period_month_name("2026-10") == "Октябрь 2026"


class TestDisplayPeriod:
    def test_rent_always_shifts_regardless_of_tenant_flag(self):
        payment = _payment()
        tenant = _tenant(invoice_operations_advance_billing=False)
        assert _display_period(payment, "rent", tenant) == "2026-10"

    def test_operations_shifts_only_with_tenant_flag(self):
        payment = _payment()
        tenant_off = _tenant(invoice_operations_advance_billing=False)
        tenant_on = _tenant(invoice_operations_advance_billing=True)
        assert _display_period(payment, "operations", tenant_off) == "2026-09"
        assert _display_period(payment, "operations", tenant_on) == "2026-10"

    def test_utilities_never_shifts(self):
        payment = _payment()
        tenant = _tenant(invoice_operations_advance_billing=True)
        assert _display_period(payment, "utilities", tenant) == "2026-09"


class TestBuildWhatsappMessageUsesShiftedPeriod:
    def test_default_template_shows_shifted_period_for_rent(self, db_session):
        payment = _payment()
        tenant = _tenant()
        with patch(
            "app.services.message_builder.get_trc_for_tenant", return_value=None
        ), patch(
            "app.services.message_builder.get_tenant_by_id", return_value=tenant
        ), patch(
            "app.services.message_builder.TenantPayment"
        ), patch.object(
            db_session, "query"
        ) as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = payment
            message = build_whatsapp_message(
                db_session,
                tenant_id=1,
                payment_id=1,
                service_type="rent",
            )
        assert "Период: 2026-10" in message
        assert "Период: 2026-09" not in message

    def test_custom_template_period_month_name_placeholder_is_shifted(self, db_session):
        payment = _payment()
        tenant = _tenant(message_template="Счёт за {period_month_name}. {details}")
        with patch(
            "app.services.message_builder.get_trc_for_tenant", return_value=None
        ), patch(
            "app.services.message_builder.get_tenant_by_id", return_value=tenant
        ), patch.object(
            db_session, "query"
        ) as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = payment
            message = build_whatsapp_message(
                db_session,
                tenant_id=1,
                payment_id=1,
                service_type="rent",
            )
        assert "Счёт за Октябрь 2026." in message
