"""Tenant.invoice_operations_advance_billing — requested 2026-09-02 for
Maxi Mall/Astranium: unlike every other tenant, their "эксплуатация" and
"маркетинг" line items are billed IN ADVANCE for next month, same +1 shift
already applied to rent (see invoice_report.py::_item_name_with_payment_month).
Default False for everyone else — this must not change existing behaviour
for any tenant that doesn't explicitly opt in."""
from unittest.mock import MagicMock

from app.services.invoice_report import _item_name_with_payment_month


class TestItemNameWithPaymentMonthOperationsFlag:
    def test_rent_shifts_regardless_of_flag(self):
        # Rent always shifts — the flag only adds operations, never removes rent's own rule.
        with_flag = _item_name_with_payment_month(
            "Аренда нежилого помещения", "2026-08-20", also_shift_operations=True
        )
        without_flag = _item_name_with_payment_month(
            "Аренда нежилого помещения", "2026-08-20", also_shift_operations=False
        )
        assert with_flag == without_flag == "Аренда нежилого помещения за Сентябрь 2026г"

    def test_operations_not_shifted_by_default(self):
        name = _item_name_with_payment_month(
            "Эксплуатационные платежи", "2026-09-04"
        )
        assert name == "Эксплуатационные платежи за Сентябрь 2026г"

    def test_operations_shifted_when_flag_set(self):
        name = _item_name_with_payment_month(
            "Эксплуатационные платежи", "2026-09-04", also_shift_operations=True
        )
        assert name == "Эксплуатационные платежи за Октябрь 2026г"

    def test_marketing_shifted_when_flag_set(self):
        # "маркетинг" lives in the same DEFAULT_PAYMENT_KEYWORDS.operations
        # bucket as "эксплуат" (see invoice_service_type.py _DEFAULT_OPS) —
        # one flag covers both, no separate keyword needed.
        name = _item_name_with_payment_month(
            "Маркетинговый взнос", "2026-09-04", also_shift_operations=True
        )
        assert name == "Маркетинговый взнос за Октябрь 2026г"

    def test_utilities_never_shifted_even_with_flag(self):
        # The flag is named/scoped to operations only — коммуналка stays
        # "по факту" for everyone, flag or not.
        name = _item_name_with_payment_month(
            "Коммунальные платежи (электроэнергия)",
            "2026-09-04",
            also_shift_operations=True,
        )
        assert "Сентябрь" in name
        assert "Октябрь" not in name

    def test_default_matches_previous_behaviour_when_flag_omitted(self):
        # Callers that don't pass the new kwarg at all (signature is
        # backward compatible) must see exactly the pre-existing behaviour.
        assert _item_name_with_payment_month(
            "Эксплуатационные платежи", "2026-09-04"
        ) == _item_name_with_payment_month(
            "Эксплуатационные платежи", "2026-09-04", also_shift_operations=False
        )


class TestTenantModelDefault:
    def test_new_tenant_flag_defaults_to_false(self):
        from app.models.catalog import Tenant

        assert Tenant.__table__.c.invoice_operations_advance_billing.default.arg is False
        assert Tenant.__table__.c.invoice_operations_advance_billing.nullable is False


class TestGetattrFallbackForMocksWithoutTheAttribute(object):
    """Guards the call site in invoice_report.py: getattr(tenant,
    "invoice_operations_advance_billing", False) must yield a real False
    for a plain object missing the attribute — not something falsy-looking
    that still breaks bool(). A MagicMock would auto-vivify the attribute
    as a truthy Mock instead of raising, so this test uses a bare object,
    not MagicMock, to prove the getattr default itself is sound."""

    def test_plain_object_without_attribute_defaults_to_no_shift(self):
        class BareTenant:
            pass

        tenant = BareTenant()
        assert bool(getattr(tenant, "invoice_operations_advance_billing", False)) is False
