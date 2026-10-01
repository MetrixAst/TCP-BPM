"""_enrich_payment_tenant_names() must recognize a "заглушка" placeholder
name (tenant_name == counterparty_id, set by app/api/notifications.py /
ensure_payment_for_counterparty when 1С didn't return a human name for that
specific document) and backfill it from the counterparty cache — not just
treat "empty tenant_name" as the only case needing a fix.

Real bug found live on CityMall prod: the "Счета к оплате" registry showed
raw GUIDs like "2c68fb5c-5012-11f0-8725-5254001b9c43" instead of counterparty
names for rows created via the placeholder path, even after re-syncing from
1С, because the old check (`if tenant_name: continue`) skipped them — a GUID
is a non-empty string."""
from unittest.mock import patch

from app.models.payment import PaymentStatus, TenantPayment
from app.services.payment_service import PaymentService


def _payment(**kwargs) -> TenantPayment:
    defaults = dict(
        ip_name="Test IP",
        invoice_date=None,
        due_date=None,
        status=PaymentStatus.UNPAID,
        period="2026-08",
    )
    defaults.update(kwargs)
    return TenantPayment(**defaults)


class TestEnrichPlaceholderTenantNames:
    def _service(self, db_session):
        return PaymentService(db_session, tenant_id=1)

    def test_guid_placeholder_name_is_replaced_from_cache(self, db_session):
        cp_id = "2c68fb5c-5012-11f0-8725-5254001b9c43"
        payment = _payment(counterparty_id=cp_id, tenant_name=cp_id)
        service = self._service(db_session)
        with patch.object(
            service,
            "_counterparty_meta_index",
            return_value={cp_id: {"name": "ИП Ибрагимов", "bin": "810617300549"}},
        ):
            service._enrich_payment_tenant_names([payment])
        assert payment.tenant_name == "ИП Ибрагимов"

    def test_guid_placeholder_matches_case_insensitively(self, db_session):
        cp_id = "2C68FB5C-5012-11F0-8725-5254001B9C43"
        payment = _payment(counterparty_id=cp_id, tenant_name=cp_id.lower())
        service = self._service(db_session)
        with patch.object(
            service,
            "_counterparty_meta_index",
            return_value={cp_id.lower(): {"name": "ИП Ибрагимов", "bin": ""}},
        ):
            service._enrich_payment_tenant_names([payment])
        assert payment.tenant_name == "ИП Ибрагимов"

    def test_empty_tenant_name_still_backfilled(self, db_session):
        cp_id = "some-cp-id"
        payment = _payment(counterparty_id=cp_id, tenant_name="")
        service = self._service(db_session)
        with patch.object(
            service,
            "_counterparty_meta_index",
            return_value={cp_id: {"name": "ТОО Ромашка", "bin": ""}},
        ):
            service._enrich_payment_tenant_names([payment])
        assert payment.tenant_name == "ТОО Ромашка"

    def test_real_name_is_never_overwritten(self, db_session):
        cp_id = "some-cp-id"
        payment = _payment(counterparty_id=cp_id, tenant_name="ИП Настоящее Имя")
        service = self._service(db_session)
        with patch.object(
            service,
            "_counterparty_meta_index",
            return_value={cp_id: {"name": "Другое Имя Из Кэша", "bin": ""}},
        ):
            service._enrich_payment_tenant_names([payment])
        assert payment.tenant_name == "ИП Настоящее Имя"

    def test_no_cache_entry_leaves_guid_placeholder_untouched(self, db_session):
        cp_id = "unknown-cp-id"
        payment = _payment(counterparty_id=cp_id, tenant_name=cp_id)
        service = self._service(db_session)
        with patch.object(service, "_counterparty_meta_index", return_value={}):
            service._enrich_payment_tenant_names([payment])
        assert payment.tenant_name == cp_id
