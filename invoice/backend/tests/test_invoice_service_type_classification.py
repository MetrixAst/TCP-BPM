"""Тип счёта: аренда / ком.услуги / маркетинг (бывш. эксплуатация) / вывеска / АССП.

Строки для «вывеска» и «АССП» — реальные данные, снятые напрямую с Nova
(org 118, CityMall Shymkent), контрагент ИП Ибрагимов, счета от 2026-08-20:
- "Размещение вывески"
- "АССП. Возмещение затрат услуги АССП." — обрати внимание, реальное
  написание "АССП" (два "С"), keyword должен матчить именно так.
См. обсуждение редизайна реестра от 2026-08-25.
"""
from app.services.invoice_service_type import (
    DEFAULT_PAYMENT_KEYWORDS,
    format_service_types_label,
    resolve_invoice_service_type,
    resolve_invoice_service_types,
)


def _items(*names):
    return [{"name": n} for n in names]


class TestRealCityMallInvoices:
    """Каждый счёт ИП Ибрагимова (CityMall, 2026-08-20) — отдельный документ
    с одной строкой; проверяем, что каждая строка классифицируется верно."""

    def test_rent_line(self):
        items = _items(
            "Аренда нежилого помещения по адресу г.Шымкент, "
            "мкрн.Туран,ул.Новостройки, здание 177А"
        )
        assert resolve_invoice_service_types(items) == ["rent"]

    def test_internet_line_is_utilities(self):
        items = _items(
            "Интернет. Возмещение затрат услуги технической поддержки "
            "Интернет-канала"
        )
        assert resolve_invoice_service_types(items) == ["utilities"]

    def test_signage_line(self):
        items = _items("Размещение вывески")
        assert resolve_invoice_service_types(items) == ["signage"]

    def test_assp_line_double_s_spelling(self):
        items = _items("АССП. Возмещение затрат услуги АССП.")
        assert resolve_invoice_service_types(items) == ["assp"]


class TestMultiTypeInvoice:
    def test_rent_and_utilities_in_one_invoice_both_detected_in_order(self):
        items = _items("Аренда торговой площади", "Коммунальные услуги за август")
        assert resolve_invoice_service_types(items) == ["rent", "utilities"]

    def test_order_is_stable_regardless_of_line_order(self):
        items = _items("Услуги АССП", "Размещение вывески", "Аренда помещения")
        assert resolve_invoice_service_types(items) == ["rent", "signage", "assp"]


class TestFormatServiceTypesLabel:
    def test_single_type(self):
        assert format_service_types_label(["rent"]) == "rent"

    def test_multiple_types_comma_joined(self):
        assert format_service_types_label(["rent", "utilities"]) == "rent,utilities"

    def test_empty_is_unknown_not_blank(self):
        assert format_service_types_label([]) == "unknown"


class TestResolveInvoiceServiceTypeSingular:
    def test_no_lines_is_unknown(self):
        assert resolve_invoice_service_type([]) == "unknown"

    def test_unrecognized_line_is_unknown(self):
        assert resolve_invoice_service_type(_items("Прочие услуги")) == "unknown"


class TestDefaultKeywords:
    def test_utilities_keywords_include_internet(self):
        assert "интернет" in DEFAULT_PAYMENT_KEYWORDS.utilities

    def test_signage_and_assp_keywords_present(self):
        assert DEFAULT_PAYMENT_KEYWORDS.signage == ("вывеск",)
        assert DEFAULT_PAYMENT_KEYWORDS.assp == ("ассп",)
