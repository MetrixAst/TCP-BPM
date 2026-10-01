"""Контрагент, поставленный на паузу (CounterpartyPhone.auto_notify_paused —
кнопка «Остановить авто-напоминания» в invoice-client), должен пропускаться
целиком в AutoNotificationService.run_for_tenant — все service_type и счета,
без единой отправки. Ручную отправку и массовую /send-debtors это не
затрагивает (они не используют _paused_counterparty_ids).

Отдельно — Tenant.auto_notify_paused («Отключить авто-напоминания для всех»)
останавливает run_for_tenant для арендатора целиком, ещё до обращения к 1С."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.models.catalog import CounterpartyPhone, TRC, Tenant
from app.services.auto_notification_service import (
    AutoNotificationService,
    _paused_counterparty_ids,
)


def make_trc_tenant(db_session, trc_name="Test TRC"):
    trc = TRC(name=trc_name, is_active=True)
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


class TestPausedCounterpartyIds:
    def test_returns_normalized_ids_of_paused_rows_only(self, db_session):
        trc, _tenant = make_trc_tenant(db_session)
        db_session.add_all(
            [
                CounterpartyPhone(
                    trc_id=trc.id, one_c_counterparty_id="CP-Paused", phone="",
                    auto_notify_paused=True,
                ),
                CounterpartyPhone(
                    trc_id=trc.id, one_c_counterparty_id="CP-Active", phone="77001234567",
                    auto_notify_paused=False,
                ),
            ]
        )
        db_session.commit()

        result = _paused_counterparty_ids(db_session, trc.id)
        assert result == {"cp-paused"}

    def test_empty_when_nothing_paused(self, db_session):
        trc, _tenant = make_trc_tenant(db_session)
        result = _paused_counterparty_ids(db_session, trc.id)
        assert result == set()

    def test_scoped_to_trc(self, db_session):
        trc1, _t1 = make_trc_tenant(db_session, "Test TRC 1")
        trc2, _t2 = make_trc_tenant(db_session, "Test TRC 2")
        db_session.add(
            CounterpartyPhone(
                trc_id=trc1.id, one_c_counterparty_id="CP-1", phone="",
                auto_notify_paused=True,
            )
        )
        db_session.commit()

        assert _paused_counterparty_ids(db_session, trc1.id) == {"cp-1"}
        assert _paused_counterparty_ids(db_session, trc2.id) == set()


class TestRunForTenantSkipsPausedCounterparty:
    def _fake_invoice(self, cp_id: str):
        return SimpleNamespace(
            counterparty_id=cp_id,
            counterparty_name="Debtor LLP",
            id="INV-1",
            date="2026-09-01",
            due_date=None,
            payment_status="unpaid",
            paid_amount=0,
            amount=1000,
        )

    def test_paused_counterparty_produces_zero_sends(self, db_session):
        trc, tenant = make_trc_tenant(db_session)
        db_session.add(
            CounterpartyPhone(
                trc_id=trc.id,
                one_c_counterparty_id="CP-9",
                phone="",
                auto_notify_paused=True,
            )
        )
        db_session.commit()

        fake_client = SimpleNamespace(
            get_invoices=lambda **kwargs: [self._fake_invoice("CP-9")],
        )
        fake_integration = SimpleNamespace(client=fake_client)

        with patch(
            "app.services.auto_notification_service.get_tenant_by_id",
            return_value=tenant,
        ), patch(
            "app.services.auto_notification_service.get_integration_for_tenant",
            return_value=fake_integration,
        ), patch(
            "app.services.auto_notification_service.get_trc_id_for_tenant",
            return_value=trc.id,
        ), patch(
            "app.services.auto_notification_service._warn_if_whatsapp_instance_not_authorized",
        ), patch.object(
            AutoNotificationService, "_refresh_tenant_data_for_check",
        ), patch.object(
            AutoNotificationService, "_send_one",
        ) as mock_send_one:
            service = AutoNotificationService(db_session)
            sent = service.run_for_tenant(tenant.id, can_send=True)

        assert sent == 0
        mock_send_one.assert_not_called()

    def test_unpaused_counterparty_still_gets_sent_one_called(self, db_session):
        """Контроль: без паузы тот же счёт доходит до _send_one (не сломали
        обычный путь новым фильтром).

        astana_today() is frozen to the invoice's due date (2026-09-05, the
        5th of the invoice's month — Tenant has no invoice_due_day set, so
        tenant_due_day_for_service falls back to its default=5) so the
        _pick_triggers_for_run offset is deterministically 0 (due-day
        reminder), regardless of the real calendar date the suite runs on.
        Previously this depended on wall-clock "today" landing on one of 6
        specific days relative to the hardcoded invoice date and started
        failing (assert 0 == 1) once real time moved past that window —
        the same freeze-time pattern test_whatsapp_resilience.py already
        uses for this exact reason."""
        trc, tenant = make_trc_tenant(db_session)

        fake_client = SimpleNamespace(
            get_invoices=lambda **kwargs: [self._fake_invoice("CP-10")],
        )
        fake_integration = SimpleNamespace(client=fake_client)

        with patch(
            "app.services.auto_notification_service.get_tenant_by_id",
            return_value=tenant,
        ), patch(
            "app.services.auto_notification_service.get_integration_for_tenant",
            return_value=fake_integration,
        ), patch(
            "app.services.auto_notification_service.get_trc_id_for_tenant",
            return_value=trc.id,
        ), patch(
            "app.services.auto_notification_service._warn_if_whatsapp_instance_not_authorized",
        ), patch.object(
            AutoNotificationService, "_refresh_tenant_data_for_check",
        ), patch(
            "app.services.auto_notification_service.astana_today",
            return_value=date(2026, 9, 5),
        ), patch(
            "app.services.auto_notification_service.invoice_service_types_from_1c",
            return_value=["rent"],
        ), patch(
            "app.services.auto_notification_service.filter_service_types",
            return_value=["rent"],
        ), patch(
            "app.services.auto_notification_service._resolve_auto_notify_phone",
            return_value="77001234567",
        ), patch.object(
            AutoNotificationService, "_send_one", return_value=True,
        ) as mock_send_one:
            service = AutoNotificationService(db_session)
            sent = service.run_for_tenant(tenant.id, can_send=True)

        assert sent == 1
        mock_send_one.assert_called_once()


class TestRunForTenantSkipsWhenTenantWidePaused:
    def test_returns_zero_without_touching_1c(self, db_session):
        trc, tenant = make_trc_tenant(db_session)
        tenant.auto_notify_paused = True
        db_session.commit()

        with patch(
            "app.services.auto_notification_service.get_tenant_by_id",
            return_value=tenant,
        ), patch(
            "app.services.auto_notification_service.get_integration_for_tenant",
        ) as mock_get_integration:
            service = AutoNotificationService(db_session)
            sent = service.run_for_tenant(tenant.id, can_send=True)

        assert sent == 0
        mock_get_integration.assert_not_called()
