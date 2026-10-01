"""get_payments() must show/count one row per real invoice (invoice_id),
matching the same dedup already used for analytics cards (_get_analytics_from_db).

Real bug found live on CityMall prod: the "Не оплачено" analytics card showed
188, but the table right below it said "Показано 1–20 из 263" for the same
filter — a raw row count, not deduped by invoice_id. Root cause: duplicate
TenantPayment rows for the same invoice_id (a "заглушка" placeholder created
by /notifications/send before the real sync landed, sitting next to the
fully-synced row for the same document) and orphan rows with no invoice_id at
all were being counted/listed as-is in get_payments(), while
_get_analytics_from_db() already deduped them away. Also verifies the
surviving row is the COMPLETE one (has amount/service_type), not whichever
happened to sync last — otherwise a placeholder duplicate could still win and
the registry would show "—" for a type that's actually known.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.core.security import create_tenant_portal_token
from app.models.catalog import TRC, Tenant
from app.models.payment import PaymentStatus, TenantPayment
from app.schemas.payment import PaymentFilter
from app.services.payment_service import PaymentService

# _enrich_payment_tenant_names() unconditionally queries CounterpartyCache (a
# Postgres-only JSONB column, not renderable against this in-memory SQLite
# test DB — see test_get_payments_service_type_param.py's own comment on
# this). Every test payment here already has tenant_name set (or is asserting
# on the raw-GUID-vs-real-name distinction directly), so the enrichment is a
# no-op either way; patch out the DB call it doesn't need rather than skip it.


@pytest.fixture(autouse=True)
def _no_counterparty_cache_lookup():
    with patch(
        "app.services.payment_service.PaymentService._counterparty_meta_index",
        return_value={},
    ):
        yield


def make_trc_tenant(db_session):
    trc = TRC(name="Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return trc, tenant


def auth_headers(tenant, trc):
    token = create_tenant_portal_token(tenant.id, trc.id)
    return {"Authorization": f"Bearer {token}"}


def _payment(tenant, **overrides):
    defaults = dict(
        tenant_id=tenant.id,
        ip_name=tenant.legal_name,
        tenant_name="ACME LLP",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 10),
        status=PaymentStatus.UNPAID,
        period="2026-08",
    )
    defaults.update(overrides)
    return TenantPayment(**defaults)


class TestGetPaymentsDedupesByInvoiceId:
    def test_duplicate_rows_for_same_invoice_counted_once(self, client, db_session):
        trc, tenant = make_trc_tenant(db_session)
        cp_id = "2c68fb5c-5012-11f0-8725-5254001b9c43"
        # Заглушка (создана /notifications/send до синка): без суммы/типа.
        db_session.add(
            _payment(
                tenant,
                invoice_id="INV-1",
                counterparty_id=cp_id,
                tenant_name=cp_id,
                amount=None,
                service_type=None,
            )
        )
        # Настоящая, полностью засинканная строка того же счёта.
        db_session.add(
            _payment(
                tenant,
                invoice_id="INV-1",
                counterparty_id=cp_id,
                tenant_name="ИП Ибрагимов",
                amount=150000,
                service_type="rent",
            )
        )
        # Другой, не связанный счёт — не должен пострадать от дедупа.
        db_session.add(_payment(tenant, invoice_id="INV-2", amount=50000, service_type="utilities"))
        db_session.commit()

        response = client.get(
            "/api/payments",
            params={"period": "2026-08"},
            headers=auth_headers(tenant, trc),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        items_by_invoice = {item["invoice_id"]: item for item in body["items"]}
        assert set(items_by_invoice) == {"INV-1", "INV-2"}
        # Выжила ПОЛНАЯ строка, а не заглушка с GUID вместо имени.
        assert items_by_invoice["INV-1"]["tenant_name"] == "ИП Ибрагимов"
        assert items_by_invoice["INV-1"]["service_type"] == "rent"

    def test_rows_without_invoice_id_are_excluded_like_in_analytics(self, client, db_session):
        trc, tenant = make_trc_tenant(db_session)
        db_session.add(_payment(tenant, invoice_id=None, amount=10000))
        db_session.add(_payment(tenant, invoice_id="", amount=10000))
        db_session.add(_payment(tenant, invoice_id="INV-REAL", amount=10000))
        db_session.commit()

        response = client.get(
            "/api/payments",
            params={"period": "2026-08"},
            headers=auth_headers(tenant, trc),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["invoice_id"] == "INV-REAL"

    def test_table_total_matches_analytics_unpaid_count(self, db_session):
        """Тот самый кейс с прода: карточка "Не оплачено" и таблица под ней
        должны сходиться, когда за одним invoice_id стоит и заглушка, и
        реальная строка."""
        trc, tenant = make_trc_tenant(db_session)
        service = PaymentService(db_session, tenant_id=tenant.id)
        service._counterparty_meta_index = lambda: {}

        for i in range(3):
            inv = f"INV-DUP-{i}"
            db_session.add(
                _payment(tenant, invoice_id=inv, amount=None, service_type=None)
            )
            db_session.add(
                _payment(
                    tenant,
                    invoice_id=inv,
                    amount=100000,
                    paid_amount=0,
                    service_type="rent",
                    status=PaymentStatus.UNPAID,
                )
            )
        db_session.commit()

        analytics = service.get_analytics(PaymentFilter(period="2026-08", page=1, page_size=50))
        payments, total = service.get_payments(
            PaymentFilter(period="2026-08", status="unpaid", page=1, page_size=50)
        )

        assert analytics.unpaid == 3
        assert total == 3
        assert len(payments) == 3
