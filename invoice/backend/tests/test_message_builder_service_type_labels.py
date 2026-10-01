"""service_type_label() only mapped rent/utilities/operations
(_SERVICE_TYPE_LABELS in message_builder.py) — signage/assp/debt/other
resolved to "", so the "Услуга: ..." line and the {service_type}/
{service_type_label} template placeholders silently went blank in the
actual WhatsApp text for those 4 types, while the frontend
(counterpartyPhoneUtils.ts) and payment_service.py._PAYMENT_TYPE_LABELS
both already had all 7 labels correct."""
from unittest.mock import MagicMock, patch

from app.services.message_builder import build_whatsapp_message, service_type_label


class TestServiceTypeLabel:
    def test_rent(self):
        assert service_type_label("rent") == "Аренда"

    def test_utilities(self):
        assert service_type_label("utilities") == "Коммунальные услуги"

    def test_operations(self):
        assert service_type_label("operations") == "Эксплуатация и маркетинг"

    def test_signage(self):
        assert service_type_label("signage") == "Вывеска"

    def test_assp(self):
        assert service_type_label("assp") == "АССП"

    def test_debt(self):
        assert service_type_label("debt") == "Долг пред. периода"

    def test_other(self):
        assert service_type_label("other") == "Прочее"

    def test_unknown_or_missing_stays_empty(self):
        assert service_type_label("unknown") == ""
        assert service_type_label(None) == ""


class TestBuildWhatsappMessageServiceLine:
    def test_signage_invoice_shows_signage_label_not_blank(self, db_session):
        tenant = MagicMock()
        tenant.message_template = None
        tenant.name = "Maxi Mall"
        with patch(
            "app.services.message_builder.get_trc_for_tenant", return_value=None
        ), patch(
            "app.services.message_builder.get_tenant_by_id", return_value=tenant
        ):
            message = build_whatsapp_message(
                db_session,
                tenant_id=1,
                invoice_number="INV-1",
                service_type="signage",
            )
        assert "Услуга: Вывеска" in message
        assert "Услуга: Аренда" not in message
