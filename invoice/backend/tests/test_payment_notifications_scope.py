"""GET /api/payments/{id}/notifications used to have no auth dependency at all —
any anonymous caller could enumerate sequential payment_id values and harvest
phone numbers/notification history across every tenant (IDOR, see audit from
2026-08-25). These tests pin the fix: auth required, and a payment belonging
to a different tenant must 404 rather than leak."""

from datetime import date

from app.core.security import create_tenant_portal_token
from app.models.catalog import TRC, Tenant
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.payment import PaymentStatus, TenantPayment


def make_trc(db_session, **overrides) -> TRC:
    defaults = dict(name="Test TRC", is_active=True)
    defaults.update(overrides)
    trc = TRC(**defaults)
    db_session.add(trc)
    db_session.commit()
    db_session.refresh(trc)
    return trc


def make_tenant(db_session, trc: TRC, **overrides) -> Tenant:
    defaults = dict(
        trc_id=trc.id,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        is_active=True,
    )
    defaults.update(overrides)
    tenant = Tenant(**defaults)
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def make_payment(db_session, ip_name: str, **overrides) -> TenantPayment:
    defaults = dict(
        ip_name=ip_name,
        tenant_name=ip_name,
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
        status=PaymentStatus.UNPAID,
        period="2026-01",
    )
    defaults.update(overrides)
    payment = TenantPayment(**defaults)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    db_session.add(
        Notification(
            payment_id=payment.id,
            notification_type=NotificationType.WEEK_BEFORE,
            status=NotificationStatus.SENT,
        )
    )
    db_session.commit()
    return payment


def auth_headers(tenant, trc):
    token = create_tenant_portal_token(tenant.id, trc.id)
    return {"Authorization": f"Bearer {token}"}


def test_payment_notifications_requires_auth(client, db_session):
    trc = make_trc(db_session)
    tenant = make_tenant(db_session, trc, legal_name="Owner LLP")
    payment = make_payment(db_session, ip_name="Owner LLP", tenant_id=tenant.id)

    response = client.get(f"/api/payments/{payment.id}/notifications")

    assert response.status_code == 401


def test_payment_notifications_rejects_other_tenant(client, db_session):
    trc = make_trc(db_session)
    owner = make_tenant(db_session, trc, legal_name="Owner LLP", portal_username="owner")
    other = make_tenant(
        db_session, trc, legal_name="Other LLP", portal_username="other", name="Other"
    )
    payment = make_payment(db_session, ip_name="Owner LLP", tenant_id=owner.id)

    response = client.get(
        f"/api/payments/{payment.id}/notifications",
        headers=auth_headers(other, trc),
    )

    assert response.status_code == 404


def test_payment_notifications_allows_owning_tenant(client, db_session):
    trc = make_trc(db_session)
    owner = make_tenant(db_session, trc, legal_name="Owner LLP", portal_username="owner")
    payment = make_payment(db_session, ip_name="Owner LLP", tenant_id=owner.id)

    response = client.get(
        f"/api/payments/{payment.id}/notifications",
        headers=auth_headers(owner, trc),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1


def test_payment_notifications_same_legal_name_does_not_leak(client, db_session):
    """The whole reason tenant_id (FK) replaced ip_name==legal_name matching:
    two tenants can share a legal_name (typo, copy-paste onboarding, same
    company renting in two TRCs) — that must not let one see the other's
    payment notifications. See audit from 2026-08-25."""
    trc = make_trc(db_session)
    owner = make_tenant(
        db_session, trc, legal_name="Shared Name LLP", portal_username="owner"
    )
    lookalike = make_tenant(
        db_session,
        trc,
        legal_name="Shared Name LLP",
        portal_username="lookalike",
        name="Lookalike",
    )
    payment = make_payment(db_session, ip_name="Shared Name LLP", tenant_id=owner.id)

    response = client.get(
        f"/api/payments/{payment.id}/notifications",
        headers=auth_headers(lookalike, trc),
    )

    assert response.status_code == 404


def test_payment_notifications_missing_payment_404(client, db_session):
    trc = make_trc(db_session)
    tenant = make_tenant(db_session, trc, legal_name="Owner LLP", portal_username="owner")

    response = client.get(
        "/api/payments/999999/notifications",
        headers=auth_headers(tenant, trc),
    )

    assert response.status_code == 404
