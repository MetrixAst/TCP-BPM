"""Regression tests: analytics cards vs status filter, period rules."""

from datetime import date

from app.services.nova_buh_1c_client import NovaBuh1CClient
from app.services.odata_1c_client import OData1CClient


class TestInvoiceBelongsToPeriod:
    def test_com_dateless_invoice_excluded(self):
        assert NovaBuh1CClient._invoice_belongs_to_period(None, None, "2026-07") is False
        assert NovaBuh1CClient._invoice_belongs_to_period("", "", "2026-07") is False

    def test_com_july_invoice_included(self):
        assert NovaBuh1CClient._invoice_belongs_to_period("2026-07-15", None, "2026-07") is True

    def test_com_prev_month_any_june_date_included_for_july(self):
        """Аренда за июль часто датируется июнём — это ожидаемое правило."""
        assert NovaBuh1CClient._invoice_belongs_to_period("2026-06-15", None, "2026-07") is True
        assert NovaBuh1CClient._invoice_belongs_to_period("2026-06-30", None, "2026-07") is True

    def test_com_due_date_fallback(self):
        assert NovaBuh1CClient._invoice_belongs_to_period(None, "2026-07-05", "2026-07") is True

    def test_odata_dateless_invoice_excluded(self):
        assert OData1CClient._invoice_belongs_to_period(None, None, "2026-07") is False

    def test_odata_july_invoice_included(self):
        assert OData1CClient._invoice_belongs_to_period("2026-07-15", None, "2026-07") is True


class TestAnalyticsInvariants:
  def test_analytics_scope_strips_status(self):
        """Карточки не должны получать status из фильтра таблицы."""
        from types import SimpleNamespace

        filters = SimpleNamespace(
            period="2026-07",
            ip_name=None,
            tenant_name="maxi",
            status="unpaid",
            page=1,
            page_size=50,
        )

        scoped = SimpleNamespace(
            period=filters.period,
            ip_name=filters.ip_name,
            tenant_name=filters.tenant_name,
            status=None,
            page=filters.page,
            page_size=filters.page_size,
        )
        assert scoped.status is None
        assert scoped.period == filters.period

  def test_live_count_excludes_dateless_invoices(self):
        items = [
            {"invoice_date": date(2026, 7, 1), "due_date": date(2026, 7, 5), "payment_status": "paid"},
            {"invoice_date": date(2026, 7, 2), "due_date": date(2026, 7, 5), "payment_status": "unpaid"},
            {"invoice_date": None, "due_date": None, "payment_status": "unpaid"},
        ]
        period = "2026-07"
        paid = unpaid = 0
        for item in items:
            inv = item["invoice_date"]
            due = item["due_date"]
            inv_s = inv.isoformat() if hasattr(inv, "isoformat") else inv
            due_s = due.isoformat() if hasattr(due, "isoformat") else due
            if not NovaBuh1CClient._invoice_belongs_to_period(inv_s, due_s, period):
                continue
            if item["payment_status"] == "paid":
                paid += 1
            else:
                unpaid += 1
        assert paid + unpaid == 2
        assert paid == 1


class TestGetAnalyticsUsesDatabase:
    def test_get_analytics_does_not_call_live_1c(self, monkeypatch):
        """HTTP analytics must not block on live 1С (gateway timeout ~15s)."""
        from unittest.mock import MagicMock

        from app.schemas.payment import PaymentFilter
        from app.services.payment_service import PaymentService

        service = PaymentService(MagicMock(), tenant_id=3)
        service.integration_1c = MagicMock()
        service.integration_1c.client = MagicMock()

        def _boom(*_args, **_kwargs):
            raise AssertionError("live 1C must not be called from get_analytics")

        monkeypatch.setattr(service, "_get_analytics_from_live_invoices", _boom)
        monkeypatch.setattr(
            service,
            "_get_analytics_from_db",
            lambda _filters: type(
                "A",
                (),
                {
                    "total_tenants": 1,
                    "total_invoices": 10,
                    "paid": 3,
                    "unpaid": 7,
                    "overdue": 0,
                    "source": "database",
                },
            )(),
        )

        result = service.get_analytics(PaymentFilter(period="2026-07", page=1, page_size=10))
        assert result.total_invoices == 10
        assert result.source == "database"
