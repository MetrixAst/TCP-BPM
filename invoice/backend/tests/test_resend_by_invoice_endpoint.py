"""POST /admin/trcs/{trc_id}/resend-by-invoice.

2026-09-09 incident follow-up: 104 of 111 bulk WhatsApp sends never
delivered, but their Notification rows in the DB already show DELIVERED
(set optimistically before the 2026-09-10 delivery-tracking fix — see
tests/test_whatsapp_resilience.py). A generic "resend all FAILED" feature
can't find these at all, since their stored status is wrong in the
*opposite* direction. This endpoint instead takes an explicit
(phone, invoice_id) list — cross-checked directly against Green API's own
GetChatHistory, not our DB (see scripts/maxi_mall_2026_09_09_stuck_messages.json)
— and re-queues each one through the exact same Kafka whatsapp_send path as
a normal send, so it inherits the new pacing/daily-cap for free instead of
looping synchronously in the request (which would just repeat the
incident)."""
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.catalog import AdminUser, TRC, Tenant
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.payment import PaymentStatus, TenantPayment


def _make_trc(db_session) -> TRC:
    trc = TRC(name="Resend Test TRC", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def _make_tenant(db_session, trc: TRC) -> Tenant:
    tenant = Tenant(
        trc_id=trc.id,
        name="Resend Test Tenant",
        legal_name="Resend Test Tenant LLP",
        one_c_login="",
        one_c_password="",
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _make_payment(db_session, tenant: Tenant, invoice_id: str, **overrides) -> TenantPayment:
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id=invoice_id,
        ip_name="Арендатор",
        tenant_name="ООО Ромашка",
        invoice_date=date(2026, 9, 1),
        due_date=date(2026, 9, 5),
        status=PaymentStatus.OVERDUE,
        period="2026-09",
        amount=150000,
        counterparty_id="cp-1",
        service_type="rent",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


def _super_admin_headers(db_session) -> dict:
    admin = AdminUser(
        username="super_admin_resend_test",
        password_hash=hash_password("pw"),
        is_active=True,
        is_super=True,
    )
    db_session.add(admin)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(admin.username)}"}


@pytest.fixture(autouse=True)
def _kafka_enabled_and_queue_mocked():
    """Real Kafka/Green API must never be touched from a test — force the
    'queued via Kafka' branch of NotificationService.send_notification and
    stub the actual publish call."""
    with patch.object(settings, "KAFKA_ENABLED", True), patch(
        "app.services.job_queue.enqueue_whatsapp_job", return_value=True
    ) as enqueue_mock:
        yield enqueue_mock


class TestResendByInvoice:
    def test_queues_each_valid_item_through_kafka(self, client, db_session, _kafka_enabled_and_queue_mocked):
        trc = _make_trc(db_session)
        tenant = _make_tenant(db_session, trc)
        _make_payment(db_session, tenant, "inv-1")
        _make_payment(db_session, tenant, "inv-2")
        headers = _super_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [
                {"phone": "77001234567", "invoice_id": "inv-1"},
                {"phone": "77007654321", "invoice_id": "inv-2"},
            ]},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["queued"] == 2
        assert body["skipped"] == 0
        assert all(r["outcome"] == "queued" for r in body["results"])
        assert all(r["notification_id"] for r in body["results"])
        assert _kafka_enabled_and_queue_mocked.call_count == 2

        notifications = db_session.query(Notification).all()
        assert len(notifications) == 2
        assert {n.phone_number for n in notifications} == {"77001234567", "77007654321"}

    def test_reuses_prior_notification_type_when_one_exists(self, db_session, client):
        trc = _make_trc(db_session)
        tenant = _make_tenant(db_session, trc)
        payment = _make_payment(db_session, tenant, "inv-3")
        db_session.add(Notification(
            payment_id=payment.id,
            notification_type=NotificationType.THREE_DAYS,
            status=NotificationStatus.SENT,
            phone_number="77001234567",
        ))
        db_session.commit()
        headers = _super_admin_headers(db_session)

        client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [{"phone": "77001234567", "invoice_id": "inv-3"}]},
            headers=headers,
        )

        new_notification = (
            db_session.query(Notification)
            .filter(Notification.payment_id == payment.id)
            .order_by(Notification.id.desc())
            .first()
        )
        assert new_notification.notification_type == NotificationType.THREE_DAYS

    def test_invalid_phone_is_skipped_without_creating_a_notification(self, db_session, client):
        """Real 2026-09-09 data had two rows with phone == '116' -- garbage,
        not a real number. Must not burn a send/daily-cap slot on it."""
        trc = _make_trc(db_session)
        tenant = _make_tenant(db_session, trc)
        _make_payment(db_session, tenant, "inv-4")
        headers = _super_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [{"phone": "116", "invoice_id": "inv-4"}]},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["queued"] == 0
        assert body["skipped"] == 1
        assert body["results"][0]["outcome"] == "invalid_phone"
        assert db_session.query(Notification).count() == 0

    def test_unknown_invoice_id_is_skipped(self, db_session, client):
        trc = _make_trc(db_session)
        _make_tenant(db_session, trc)
        headers = _super_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [{"phone": "77001234567", "invoice_id": "does-not-exist"}]},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["outcome"] == "invoice_not_found"

    def test_already_delivered_notification_is_not_resent(self, db_session, client):
        """Real confirmed delivery -- via the 2026-09-10 webhook fix, whose
        only match key is green_api_id_message -- must never be silently
        duplicated by an accidental repeat call to this endpoint."""
        trc = _make_trc(db_session)
        tenant = _make_tenant(db_session, trc)
        payment = _make_payment(db_session, tenant, "inv-5")
        db_session.add(Notification(
            payment_id=payment.id,
            notification_type=NotificationType.OVERDUE,
            status=NotificationStatus.DELIVERED,
            delivered_at=datetime(2026, 9, 10, 8, 0),
            green_api_id_message="3EB0REALWEBHOOKCONFIRMED",
            phone_number="77001234567",
        ))
        db_session.commit()
        headers = _super_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [{"phone": "77001234567", "invoice_id": "inv-5"}]},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["outcome"] == "already_delivered"
        assert db_session.query(Notification).count() == 1  # no new row added

    def test_optimistic_pre_fix_delivered_status_is_still_resent(self, db_session, client, _kafka_enabled_and_queue_mocked):
        """2026-09-09 incident rows: status AND delivered_at were BOTH set
        synchronously on HTTP 200 from Green API, before the 2026-09-10
        webhook fix -- see Notification.delivered_at's docstring and the old
        deliver_notification code it replaced. So delivered_at IS NOT NULL
        does not distinguish them from a real delivery either -- only
        green_api_id_message does (that column, and its one assignment, were
        both introduced by the same fix; old rows never got backfilled and
        are permanently NULL there).

        Live prod check on 2026-09-10: a first attempt at this guard used
        delivered_at IS NOT NULL and still treated all 100 remaining
        incident rows as already_delivered -- direct Green API GetChatHistory
        for one of them (notification_id=7411) showed statusMessage="sent",
        proving delivered_at=2026-09-09T07:43:18 in our own DB was exactly
        that same pre-fix optimistic value, not a real confirmation."""
        trc = _make_trc(db_session)
        tenant = _make_tenant(db_session, trc)
        payment = _make_payment(db_session, tenant, "inv-6")
        db_session.add(Notification(
            payment_id=payment.id,
            notification_type=NotificationType.OVERDUE,
            status=NotificationStatus.DELIVERED,
            delivered_at=datetime(2026, 9, 9, 7, 43, 18),
            green_api_id_message=None,
            phone_number="77001234567",
        ))
        db_session.commit()
        headers = _super_admin_headers(db_session)

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [{"phone": "77001234567", "invoice_id": "inv-6"}]},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["outcome"] == "queued"

    def test_regular_admin_forbidden(self, db_session, client):
        trc = _make_trc(db_session)
        admin = AdminUser(
            username="regular_admin_resend_test",
            password_hash=hash_password("pw"),
            is_active=True,
            is_super=False,
        )
        db_session.add(admin)
        db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(admin.username)}"}

        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": [{"phone": "77001234567", "invoice_id": "inv-1"}]},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_unknown_trc_404s(self, db_session, client):
        headers = _super_admin_headers(db_session)
        resp = client.post(
            "/api/admin/trcs/999999/resend-by-invoice",
            json={"items": [{"phone": "77001234567", "invoice_id": "inv-1"}]},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_empty_items_rejected(self, db_session, client):
        trc = _make_trc(db_session)
        headers = _super_admin_headers(db_session)
        resp = client.post(
            f"/api/admin/trcs/{trc.id}/resend-by-invoice",
            json={"items": []},
            headers=headers,
        )
        assert resp.status_code == 422
