"""_merge_supplier_requisites (nova_buh_1c_client.py) — КНП fallback chain,
extended 2026-09-02: real 1C documents (Astranium/Maxi Mall) frequently
leave "Счет.КодНазначенияПлатежа" empty, and the old fallback
(tenant.invoice_payment_knp, one flat value for every charge type) applied
855-for-everything indiscriminately. Priority is now:

1. Real 1C value already on the payload (untouched, highest priority).
2. Code default by service type, guessed from item names
   (DEFAULT_KNP_BY_SERVICE_TYPE: rent->855, operations->855, utilities->856
   — operations was 858 on 2026-09-02, changed same day to match rent's
   855 per Maxi Mall manager's request: operations/marketing should carry
   the same code as rent, not a separate one).
3. Tenant's own general fallback (invoice_payment_knp) — only for types
   outside that map (signage/assp/debt/other/unknown), exactly as before.

Applies to both COM/Nova (this module) and OData/xlsx (they share this same
function) — see companion tests in test_xlsx_invoice_pdf.py for the xlsx
side, which is unaffected (xlsx sets payment_knp itself before this ever
runs, and never carries an "items" key at this point anyway)."""
from unittest.mock import MagicMock

from app.services.nova_buh_1c_client import _merge_supplier_requisites


def _tenant(invoice_payment_knp=None):
    tenant = MagicMock()
    tenant.legal_name = "Test Supplier LLP"
    tenant.name = "Test Supplier"
    tenant.bin_value = None
    tenant.invoice_iik = None
    tenant.invoice_kbe = None
    tenant.invoice_bank_name = None
    tenant.invoice_bank_bik = None
    tenant.invoice_supplier_address = None
    tenant.invoice_contract_text = None
    tenant.invoice_payment_knp = invoice_payment_knp
    return tenant


class TestRealOneCValueAlwaysWins:
    def test_existing_payment_knp_is_never_overwritten(self):
        payload = {
            "payment_knp": "999",
            "items": [{"name": "Аренда нежилого помещения"}],
        }
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp="855"))
        assert result["payment_knp"] == "999"


class TestCodeDefaultByServiceType:
    def test_rent_item_gets_855_when_1c_and_tenant_both_empty(self):
        payload = {"payment_knp": "", "items": [{"name": "Аренда нежилого помещения"}]}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp=None))
        assert result["payment_knp"] == "855"

    def test_operations_and_marketing_items_get_855_same_as_rent(self):
        # Was 858 (2026-09-02), changed same day per Maxi Mall manager's
        # request: operations/marketing should carry the same code as
        # rent, not a separate one.
        payload = {
            "payment_knp": "",
            "items": [
                {"name": "Эксплуатационные платежи за Сентябрь 2026г"},
                {"name": "Маркетинговый взнос за Сентябрь 2026г"},
            ],
        }
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp=None))
        assert result["payment_knp"] == "855"

    def test_utilities_item_gets_856(self):
        payload = {"payment_knp": "", "items": [{"name": "Коммунальные платежи (электроэнергия)"}]}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp=None))
        assert result["payment_knp"] == "856"

    def test_code_default_wins_over_tenants_own_general_fallback(self):
        # This is the actual bug being fixed: previously EVERY charge type
        # got the tenant's one flat default, even one that doesn't match
        # what the item's own type should carry. Use a tenant default
        # deliberately different from 855 so this stays meaningful now that
        # operations and rent share the same code.
        payload = {"payment_knp": "", "items": [{"name": "Эксплуатационные платежи"}]}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp="861"))
        assert result["payment_knp"] == "855"


class TestFallsBackToTenantDefaultOutsideTheMap:
    def test_signage_falls_back_to_tenant_default(self):
        payload = {"payment_knp": "", "items": [{"name": "Размещение вывески"}]}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp="861"))
        assert result["payment_knp"] == "861"

    def test_unrecognized_item_falls_back_to_tenant_default(self):
        payload = {"payment_knp": "", "items": [{"name": "Прочие услуги без ключевых слов"}]}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp="861"))
        assert result["payment_knp"] == "861"

    def test_no_items_at_all_falls_back_to_tenant_default(self):
        # This is exactly the xlsx-payload shape at the point this function
        # runs for a "debt"/"other" row: no "items" key yet.
        payload = {"payment_knp": ""}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp="861"))
        assert result["payment_knp"] == "861"

    def test_nothing_anywhere_leaves_payment_knp_empty(self):
        payload = {"payment_knp": "", "items": [{"name": "Аренда нежилого помещения"}]}
        result = _merge_supplier_requisites(payload, _tenant(invoice_payment_knp=None))
        # Sanity check on the fixture itself is covered by the rent test
        # above; this one drops the item to prove the true empty-empty case.
        payload2 = {"payment_knp": "", "items": []}
        result2 = _merge_supplier_requisites(payload2, _tenant(invoice_payment_knp=None))
        assert result2.get("payment_knp") in (None, "")
