"""app/services/whatsapp_log_service.py — the combined WhatsApp send log
(Notification rows for manual/bulk sends + AutoNotificationLog rows for
auto-notify) shown in the admin UI.

Real gap found 2026-09-02 while adding xlsx_bulk_notify_service.py: the
1C bulk path (bulk_debtor_notify_service.py) writes BOTH a real
Notification row (the actual delivery record, picked up by _manual_query)
AND an AutoNotificationLog row (trigger_kind="bulk_<date>", purely a
same-day duplicate-send guard) for every send — _auto_query excludes rows
whose trigger_kind matches that guard pattern so they don't show up twice
in the log. xlsx_bulk_notify_service.py does exactly the same thing
(trigger_kind="xlsx_bulk_<date>"), but the exclusion pattern was
"bulk_%" (prefix-only) — "xlsx_bulk_..." doesn't start with "bulk_", so
every xlsx bulk send would have shown up twice: once as "manual" (real
Notification), once as "auto" (the guard row). Fixed by broadening the
pattern to "%bulk_%" (contains, not just starts-with)."""
from datetime import date, datetime, timezone

import pytest

from app.models.auto_notification_log import AutoNotificationLog
from app.models.catalog import TRC, Tenant
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.payment import PaymentStatus, TenantPayment
from app.services.whatsapp_log_service import get_whatsapp_log

_trc_counter = [0]


def make_tenant(db_session) -> Tenant:
    _trc_counter[0] += 1
    trc = TRC(name=f"Whatsapp Log Test TRC {_trc_counter[0]}", is_active=True)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)

    tenant = Tenant(
        trc_id=trc.id,
        name="Whatsapp Log Test Tenant",
        legal_name="Whatsapp Log Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def make_payment(db_session, tenant: Tenant, **overrides) -> TenantPayment:
    defaults = dict(
        tenant_id=tenant.id,
        invoice_id="xlsx:1:2026-09:cp-1:rent",
        ip_name="Арендатор",
        tenant_name="Арендатор",
        invoice_date=date(2026, 9, 1),
        due_date=date(2026, 9, 15),
        status=PaymentStatus.UNPAID,
        period="2026-09",
        amount=100000,
        counterparty_id="cp-1",
        service_type="rent",
        source="xlsx",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


def make_notification(db_session, payment: TenantPayment) -> Notification:
    notification = Notification(
        payment_id=payment.id,
        notification_type=NotificationType.SAME_DAY,
        status=NotificationStatus.DELIVERED,
        phone_number="+77001234567",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(notification)
    db_session.commit()
    return notification


def make_auto_log(db_session, tenant: Tenant, payment: TenantPayment, trigger_kind: str) -> AutoNotificationLog:
    log = AutoNotificationLog(
        tenant_id=tenant.id,
        counterparty_id=payment.counterparty_id,
        invoice_id=payment.invoice_id,
        service_type=payment.service_type,
        trigger_kind=trigger_kind,
        phone_number="+77001234567",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(log)
    db_session.commit()
    return log


class TestBulkGuardRowsExcludedFromLog:
    def test_1c_bulk_guard_row_not_double_counted(self, db_session):
        """Pre-existing behavior, regression guard: a real send via the 1C
        bulk path writes both a Notification (real delivery record) and an
        AutoNotificationLog guard row — the log must show it once."""
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant, invoice_id="real-1c-guid-1", source="one_c")
        make_notification(db_session, payment)
        make_auto_log(db_session, tenant, payment, trigger_kind="bulk_2026-09-02")

        entries, total = get_whatsapp_log(db_session, trc_id=tenant.trc_id)

        assert total == 1
        assert len(entries) == 1
        assert entries[0]["source"] == "manual"

    def test_xlsx_bulk_guard_row_not_double_counted(self, db_session):
        """The actual bug: same shape as above but for
        xlsx_bulk_notify_service.py's trigger_kind prefix."""
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        make_notification(db_session, payment)
        make_auto_log(db_session, tenant, payment, trigger_kind="xlsx_bulk_2026-09-02")

        entries, total = get_whatsapp_log(db_session, trc_id=tenant.trc_id)

        assert total == 1
        assert len(entries) == 1
        assert entries[0]["source"] == "manual"

    def test_real_auto_notify_trigger_still_shown(self, db_session):
        """The exclusion must stay narrow — a genuine auto-notify send
        (no separate Notification row at all) must still appear."""
        tenant = make_tenant(db_session)
        payment = make_payment(db_session, tenant)
        make_auto_log(db_session, tenant, payment, trigger_kind="before5_2026-09-15")

        entries, total = get_whatsapp_log(db_session, trc_id=tenant.trc_id)

        assert total == 1
        assert len(entries) == 1
        assert entries[0]["source"] == "auto"
