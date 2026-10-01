"""Green API resilience: транспортные ретраи и статус FAILED при неуспехе.

До этих изменений: (1) requests.post был одноразовый — временный 429/5xx/сеть
молча терял сообщение; (2) Notification.status оставался SENT навсегда, даже
если Green API отказал — "не дошло" от "пока не подтверждено" было не
отличить. См. также tests/test_bulk_debtor_notify_service_type_filter.py для
логики массовой рассылки.

Отдельный in-memory SQLite-движок только с нужными таблицами — не трогаем
conftest._TEST_TABLES, чтобы не задеть остальные тесты.
"""
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.database import Base
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.payment import PaymentStatus, TenantPayment
from app.services import whatsapp_jobs
from app.services.whatsapp_service import WhatsAppService, _build_retrying_session


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(
        bind=engine, tables=[TenantPayment.__table__, Notification.__table__]
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_notification(db_session) -> Notification:
    payment = TenantPayment(
        ip_name="ИП Тест",
        tenant_name="Арендатор",
        invoice_date=date(2026, 8, 1),
        due_date=date(2026, 8, 25),
        status=PaymentStatus.UNPAID,
        period="2026-08",
    )
    db_session.add(payment)
    db_session.commit()

    notification = Notification(
        payment_id=payment.id,
        notification_type=NotificationType.SAME_DAY,
        status=NotificationStatus.SENT,
        phone_number="77001234567",
    )
    db_session.add(notification)
    db_session.commit()
    return notification


class TestPdfMatchesInvoice:
    """Real bug found 2026-09-02 while spec-reviewing the xlsx bulk-send
    feature: files are saved via _resolve_downloads_path() (sanitizes the
    invoice_id — e.g. ":" -> "_" — for filesystem safety), but this
    function used to compare the RAW, unsanitized invoice_id against the
    sanitized filename. A real 1C GUID never contains an unsafe character,
    so sanitized == raw and the bug was invisible for the pure-1C path —
    only an xlsx-sourced id ("xlsx:5:2026-08:cp:rent") exposed it: the
    comparison always failed, silently discarding a correctly pre-rendered
    xlsx PDF on every Kafka-queued send and falling through to a live 1C
    re-fetch that can never resolve a synthetic id."""

    def test_xlsx_invoice_id_with_colons_matches_its_sanitized_filename(self):
        assert whatsapp_jobs._pdf_matches_invoice(
            "invoice_xlsx_5_2026-08_cp-1_rent.pdf",
            "xlsx:5:2026-08:cp-1:rent",
        ) is True

    def test_real_1c_guid_still_matches_unchanged(self):
        """Guard against a regression in the other direction — a real GUID
        has no characters safe_filename_component would touch, so this
        fix must be a complete no-op for the existing, working 1C path."""
        guid = "8c847e8b-cf28-11ef-8419-bca8a681a811"
        assert whatsapp_jobs._pdf_matches_invoice(f"invoice_{guid}.pdf", guid) is True

    def test_mismatched_invoice_still_rejected(self):
        assert whatsapp_jobs._pdf_matches_invoice(
            "invoice_xlsx_5_2026-08_cp-1_rent.pdf",
            "xlsx:5:2026-08:cp-1:utilities",
        ) is False

    def test_empty_invoice_id_trusts_any_file(self):
        assert whatsapp_jobs._pdf_matches_invoice("invoice_whatever.pdf", "") is True


class TestRetryingSession:
    """Green API сам рекомендует бэкофф на 429 (rate limit — 50 sendMessage/sec
    на инстанс) — без этого временный всплеск не отличить от постоянного сбоя."""

    def test_retries_on_rate_limit_and_server_errors(self):
        session = _build_retrying_session()
        adapter = session.get_adapter("https://api.greenapi.com/x")
        retry = adapter.max_retries
        assert retry.total == 3
        assert 429 in retry.status_forcelist
        for code in (500, 502, 503, 504):
            assert code in retry.status_forcelist

    def test_post_is_retried_not_just_get(self):
        # POST не ретраится в urllib3 по умолчанию (не идемпотентен) — Green
        # API методы отправки — это POST, поэтому это нужно включать явно.
        session = _build_retrying_session()
        retry = session.get_adapter("https://api.greenapi.com/x").max_retries
        assert "POST" in retry.allowed_methods

    def test_respects_retry_after_header(self):
        session = _build_retrying_session()
        retry = session.get_adapter("https://api.greenapi.com/x").max_retries
        assert retry.respect_retry_after_header is True

    def test_hang_does_not_cascade_into_multiple_full_timeouts(self):
        # Настоящий "не отвечает" (read-timeout) не должен ретраиться так же
        # охотно, как быстрый 429/5xx — иначе зависший Green API утраивает
        # время ожидания (30/120 сек за попытку) вместо того, чтобы защищать.
        session = _build_retrying_session()
        retry = session.get_adapter("https://api.greenapi.com/x").max_retries
        assert retry.connect == 1
        assert retry.read == 1
        assert retry.status == 3


class TestSetSendDelay:
    """Green API SetSettings.delaySendMessagesMilliseconds — server-side
    pacing, второй уровень защиты рядом с паузой kafka_worker."""

    def _service(self) -> WhatsAppService:
        return WhatsAppService(
            api_url="https://api.greenapi.com",
            id_instance="123",
            api_token="tok",
        )

    def test_posts_delay_to_set_settings(self):
        service = self._service()
        with patch("app.services.whatsapp_service.requests.post") as post_mock:
            post_mock.return_value = type(
                "Resp", (), {"status_code": 200, "text": "{}"}
            )()
            ok = service.set_send_delay(45000)
        assert ok is True
        url, kwargs = post_mock.call_args
        assert url[0] == "https://api.greenapi.com/waInstance123/setSettings/tok"
        assert kwargs["json"] == {"delaySendMessagesMilliseconds": 45000}

    def test_returns_false_without_credentials(self):
        service = WhatsAppService(api_url="https://api.greenapi.com", id_instance=None, api_token=None)
        with patch("app.services.whatsapp_service.requests.post") as post_mock:
            ok = service.set_send_delay(45000)
        assert ok is False
        post_mock.assert_not_called()

    def test_returns_false_on_non_200(self):
        service = self._service()
        with patch("app.services.whatsapp_service.requests.post") as post_mock:
            post_mock.return_value = type(
                "Resp", (), {"status_code": 500, "text": "boom"}
            )()
            ok = service.set_send_delay(45000)
        assert ok is False

    def test_returns_false_on_network_error(self):
        service = self._service()
        with patch(
            "app.services.whatsapp_service.requests.post",
            side_effect=ConnectionError("unreachable"),
        ):
            ok = service.set_send_delay(45000)
        assert ok is False

    def test_webhook_url_adds_outgoing_api_message_webhook_flag(self):
        """Обнаружено 2026-09-10: на реальном инстансе 720122720226
        webhookUrl был пустой, outgoingAPIMessageWebhook="no" — вебхук
        outgoingMessageStatus не приходил вообще, весь код в
        whatsapp_jobs._process_green_api_webhook был мёртвым без этого."""
        service = self._service()
        with patch("app.services.whatsapp_service.requests.post") as post_mock:
            post_mock.return_value = type(
                "Resp", (), {"status_code": 200, "text": "{}"}
            )()
            ok = service.set_send_delay(
                45000, webhook_url="https://api.invoice.metrix.com.ai/api/webhooks/green-api"
            )
        assert ok is True
        _, kwargs = post_mock.call_args
        assert kwargs["json"] == {
            "delaySendMessagesMilliseconds": 45000,
            "webhookUrl": "https://api.invoice.metrix.com.ai/api/webhooks/green-api",
            "outgoingAPIMessageWebhook": "yes",
        }

    def test_no_webhook_url_leaves_webhook_settings_untouched(self):
        """Обратная совместимость: если webhook_url не передан, в теле
        запроса нет webhookUrl/outgoingAPIMessageWebhook вообще — конфиг
        Green API вне пейсинга не трогается."""
        service = self._service()
        with patch("app.services.whatsapp_service.requests.post") as post_mock:
            post_mock.return_value = type(
                "Resp", (), {"status_code": 200, "text": "{}"}
            )()
            service.set_send_delay(45000)
        _, kwargs = post_mock.call_args
        assert kwargs["json"] == {"delaySendMessagesMilliseconds": 45000}


class TestDeliverNotificationFailureStatus:
    def test_success_keeps_sent_until_webhook_confirms_delivery(self, db_session):
        """Real incident 2026-09-09: a 200 from Green API's sendMessage used
        to be marked DELIVERED immediately here — that's "Green API accepted
        our HTTP request", not "WhatsApp actually delivered it". 104 of 111
        bulk-sent invoices showed "delivered" in our DB that day while the
        instance was actually blocked and nothing reached the recipient.
        Status must stay SENT (the default) until a real outgoingMessageStatus
        webhook confirms it — see TestProcessGreenApiWebhook below."""
        notification = _make_notification(db_session)
        fake_whatsapp = type(
            "FakeWA",
            (),
            {
                "send_message": staticmethod(lambda **kw: True),
                "last_id_message": "3EB0ABCDEF123456",
            },
        )()
        with patch.object(
            whatsapp_jobs, "get_whatsapp_for_tenant", return_value=fake_whatsapp
        ), patch.object(whatsapp_jobs, "build_whatsapp_message", return_value="msg"):
            ok = whatsapp_jobs.deliver_notification(
                db_session,
                notification_id=notification.id,
                tenant_id=1,
                file_path=None,
                counterparty_name="ООО Ромашка",
            )
        db_session.refresh(notification)
        assert ok is True
        assert notification.status == NotificationStatus.SENT
        assert notification.delivered_at is None
        assert notification.green_api_id_message == "3EB0ABCDEF123456"

    def test_green_api_failure_marks_failed_not_stuck_on_sent(self, db_session):
        """Раньше: send_message() -> False просто возвращался как False, статус
        в БД оставался SENT навсегда — не отличить от "пока не подтверждено"."""
        notification = _make_notification(db_session)
        fake_whatsapp = type(
            "FakeWA", (), {"send_message": staticmethod(lambda **kw: False)}
        )()
        with patch.object(
            whatsapp_jobs, "get_whatsapp_for_tenant", return_value=fake_whatsapp
        ), patch.object(whatsapp_jobs, "build_whatsapp_message", return_value="msg"):
            ok = whatsapp_jobs.deliver_notification(
                db_session,
                notification_id=notification.id,
                tenant_id=1,
                file_path=None,
                counterparty_name="ООО Ромашка",
            )
        db_session.refresh(notification)
        assert ok is False
        assert notification.status == NotificationStatus.FAILED
        assert notification.delivered_at is None

    def test_exception_during_send_also_marks_failed(self, db_session):
        notification = _make_notification(db_session)

        def _boom(**kw):
            raise ConnectionError("green api unreachable")

        fake_whatsapp = type("FakeWA", (), {"send_message": staticmethod(_boom)})()
        with patch.object(
            whatsapp_jobs, "get_whatsapp_for_tenant", return_value=fake_whatsapp
        ), patch.object(whatsapp_jobs, "build_whatsapp_message", return_value="msg"):
            ok = whatsapp_jobs.deliver_notification(
                db_session,
                notification_id=notification.id,
                tenant_id=1,
                file_path=None,
                counterparty_name="ООО Ромашка",
            )
        db_session.refresh(notification)
        assert ok is False
        assert notification.status == NotificationStatus.FAILED


class TestRefreshPlaceholderPayment:
    """/notifications/send создаёт для Nova-арендаторов заглушку TenantPayment
    (amount=None) когда синка ещё не было — без рефреша сообщение уходило с
    "Сумма: 0 тг" и сегодняшней датой вместо настоящего срока оплаты."""

    def _fake_integration(self, invoice_amount=167000, invoice_date="2026-08-05"):
        fake_invoice = type(
            "FakeInvoice", (), {"amount": invoice_amount, "date": invoice_date}
        )()

        class FakeClient:
            def fetch_invoice_payment_status(self, invoice_id):
                return fake_invoice

        class FakeIntegration:
            client = FakeClient()

            def close(self):
                pass

        return FakeIntegration()

    def test_fills_amount_and_due_date_for_placeholder(self, db_session):
        notification = _make_notification(db_session)
        payment = db_session.get(TenantPayment, notification.payment_id)
        payment.amount = None  # заглушка, как создаёт /notifications/send
        db_session.commit()

        with patch.object(
            whatsapp_jobs, "get_integration_for_tenant", return_value=self._fake_integration()
        ), patch.object(whatsapp_jobs, "get_tenant_by_id", return_value=None):
            whatsapp_jobs._refresh_placeholder_payment(
                db_session,
                tenant_id=1,
                payment_id=payment.id,
                invoice_id="inv-1",
                service_type="rent",
            )

        db_session.refresh(payment)
        assert payment.amount == 167000
        assert payment.invoice_date == date(2026, 8, 5)
        # due_date всегда строго позже даты счёта — здесь 5-е число ещё не
        # наступило к моменту счёта (счёт от 05.08, due_day=5), так что срок
        # остаётся в том же месяце: 2026-08-05 сам по себе не позже даты
        # счёта (равен ей), поэтому переносится на 2026-09-05.
        assert payment.due_date == date(2026, 9, 5)

    def test_backfills_real_name_and_service_type_over_guid_placeholder(self, db_session):
        """Реальный кейс: /notifications/send не получил имя от 1С и создал
        заглушку с tenant_name = counterparty_id (сырой GUID) и без
        service_type — реестр показывал GUID вместо имени и "—" вместо типа
        счёта. Живой запрос здесь уже есть (для суммы/срока) — заодно чинит и
        это, не дожидаясь обычного sync_from_1c."""
        cp_id = "2c68fb5c-5012-11f0-8725-5254001b9c43"
        notification = _make_notification(db_session)
        payment = db_session.get(TenantPayment, notification.payment_id)
        payment.amount = None
        payment.counterparty_id = cp_id
        payment.tenant_name = cp_id  # заглушка — имя не пришло от 1С
        payment.service_type = None
        db_session.commit()

        fake_invoice = type(
            "FakeInvoice",
            (),
            {
                "amount": 167000,
                "date": "2026-08-05",
                "counterparty_name": "ИП Ибрагимов",
                "items": [{"name": "Аренда нежилого помещения"}],
            },
        )()

        class FakeClient:
            def fetch_invoice_payment_status(self, invoice_id):
                return fake_invoice

        class FakeIntegration:
            client = FakeClient()

            def close(self):
                pass

        with patch.object(
            whatsapp_jobs, "get_integration_for_tenant", return_value=FakeIntegration()
        ), patch.object(whatsapp_jobs, "get_tenant_by_id", return_value=None):
            whatsapp_jobs._refresh_placeholder_payment(
                db_session,
                tenant_id=1,
                payment_id=payment.id,
                invoice_id="inv-1",
                service_type="rent",
            )

        db_session.refresh(payment)
        assert payment.tenant_name == "ИП Ибрагимов"
        assert payment.service_type == "rent"

    def test_does_not_overwrite_real_name_or_existing_service_type(self, db_session):
        notification = _make_notification(db_session)
        payment = db_session.get(TenantPayment, notification.payment_id)
        payment.amount = None
        payment.counterparty_id = "some-cp-id"
        payment.tenant_name = "Уже Настоящее Имя"
        payment.service_type = "utilities"
        db_session.commit()

        fake_invoice = type(
            "FakeInvoice",
            (),
            {
                "amount": 167000,
                "date": "2026-08-05",
                "counterparty_name": "Другое Имя От 1С",
                "items": [{"name": "Аренда"}],
            },
        )()

        class FakeClient:
            def fetch_invoice_payment_status(self, invoice_id):
                return fake_invoice

        class FakeIntegration:
            client = FakeClient()

            def close(self):
                pass

        with patch.object(
            whatsapp_jobs, "get_integration_for_tenant", return_value=FakeIntegration()
        ), patch.object(whatsapp_jobs, "get_tenant_by_id", return_value=None):
            whatsapp_jobs._refresh_placeholder_payment(
                db_session,
                tenant_id=1,
                payment_id=payment.id,
                invoice_id="inv-1",
                service_type="rent",
            )

        db_session.refresh(payment)
        assert payment.tenant_name == "Уже Настоящее Имя"
        assert payment.service_type == "utilities"

    def test_leaves_already_synced_payment_alone(self, db_session):
        """amount уже есть — значит обычный синк уже дошёл, не трогаем и не
        делаем лишний живой запрос в 1С."""
        notification = _make_notification(db_session)
        payment = db_session.get(TenantPayment, notification.payment_id)
        payment.amount = 55000
        db_session.commit()
        original_due_date = payment.due_date

        with patch.object(whatsapp_jobs, "get_integration_for_tenant") as get_integration:
            whatsapp_jobs._refresh_placeholder_payment(
                db_session,
                tenant_id=1,
                payment_id=payment.id,
                invoice_id="inv-1",
                service_type="rent",
            )
            get_integration.assert_not_called()

        db_session.refresh(payment)
        assert payment.amount == 55000
        assert payment.due_date == original_due_date

    def test_no_invoice_id_is_a_noop(self, db_session):
        notification = _make_notification(db_session)
        payment = db_session.get(TenantPayment, notification.payment_id)
        payment.amount = None
        db_session.commit()

        with patch.object(whatsapp_jobs, "get_integration_for_tenant") as get_integration:
            whatsapp_jobs._refresh_placeholder_payment(
                db_session,
                tenant_id=1,
                payment_id=payment.id,
                invoice_id=None,
                service_type="rent",
            )
            get_integration.assert_not_called()

    def test_1c_failure_does_not_raise(self, db_session):
        notification = _make_notification(db_session)
        payment = db_session.get(TenantPayment, notification.payment_id)
        payment.amount = None
        db_session.commit()

        class BoomClient:
            def fetch_invoice_payment_status(self, invoice_id):
                raise ConnectionError("1c unreachable")

        class BoomIntegration:
            client = BoomClient()

        with patch.object(
            whatsapp_jobs, "get_integration_for_tenant", return_value=BoomIntegration()
        ), patch.object(whatsapp_jobs, "get_tenant_by_id", return_value=None):
            whatsapp_jobs._refresh_placeholder_payment(
                db_session,
                tenant_id=1,
                payment_id=payment.id,
                invoice_id="inv-1",
                service_type="rent",
            )  # не должно бросить исключение

        db_session.refresh(payment)
        assert payment.amount is None  # осталась заглушка, но сообщение не упало


class TestPdfDownloadRetriesAndFallback:
    """Реальный инцидент на проде 2026-08-25: массовая рассылка 180 счетам —
    Nova (onec.buh.getpdf) отвечала 502 на PDF каждого счёта ~15 минут
    подряд. Без ретрая один сбой стоил счёта целиком: process_whatsapp_job
    возвращал False -> job улетал в Kafka-реквью без задержки между
    попытками (kafka_worker.MAX_WHATSAPP_JOB_RETRIES=3) -> все 3 попытки
    утыкались в то же окно недоступности и терялись молча."""

    def _fake_integration(self, results):
        """results: список — либо PDF-путь (str), либо Exception на каждый
        последовательный вызов get_invoice_and_download."""
        calls = {"n": 0}

        class FakeClient:
            pass

        class FakeIntegration:
            client = FakeClient()

            def get_invoice_and_download(self, invoice_id, tenant=None):
                i = calls["n"]
                calls["n"] += 1
                outcome = results[min(i, len(results) - 1)]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            def close(self):
                pass

        return FakeIntegration(), calls

    def test_succeeds_on_retry_after_transient_502(self, db_session, tmp_path):
        pdf = tmp_path / "invoice_inv-1.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        integration, calls = self._fake_integration(
            [ConnectionError("502 Bad Gateway"), str(pdf)]
        )
        with patch.object(
            whatsapp_jobs, "get_integration_for_tenant", return_value=integration
        ), patch.object(whatsapp_jobs, "get_tenant_by_id", return_value=None), patch.object(
            whatsapp_jobs.time, "sleep"
        ) as sleep_mock:
            result = whatsapp_jobs._download_invoice_pdf(
                db_session, tenant_id=1, invoice_id="inv-1"
            )
        assert result == str(pdf)
        assert calls["n"] == 2  # 1 failed attempt + 1 successful
        sleep_mock.assert_called_once()  # backoff only between attempts, not after success

    def test_gives_up_after_exhausting_retries(self, db_session):
        integration, calls = self._fake_integration(
            [ConnectionError("502 Bad Gateway")] * whatsapp_jobs._PDF_DOWNLOAD_RETRIES
        )
        with patch.object(
            whatsapp_jobs, "get_integration_for_tenant", return_value=integration
        ), patch.object(whatsapp_jobs, "get_tenant_by_id", return_value=None), patch.object(
            whatsapp_jobs.time, "sleep"
        ):
            result = whatsapp_jobs._download_invoice_pdf(
                db_session, tenant_id=1, invoice_id="inv-1"
            )
        assert result is None
        assert calls["n"] == whatsapp_jobs._PDF_DOWNLOAD_RETRIES  # no extra calls past the cap

    def test_resolve_job_file_path_falls_back_to_cache_when_live_download_fails(
        self, db_session
    ):
        with patch.object(
            whatsapp_jobs, "_download_invoice_pdf", return_value=None
        ) as download_mock, patch.object(
            whatsapp_jobs, "find_cached_invoice_pdf", return_value="/cache/invoice_inv-1.pdf"
        ) as cache_mock:
            result = whatsapp_jobs._resolve_job_file_path(
                db_session,
                tenant_id=1,
                file_path=None,
                invoice_id="inv-1",
                payment_id=None,
            )
        assert result == "/cache/invoice_inv-1.pdf"
        download_mock.assert_called_once()
        cache_mock.assert_called_once()
        assert cache_mock.call_args.args[0] == "inv-1"
        assert cache_mock.call_args.kwargs.get("tenant_id") == 1

    def test_resolve_job_file_path_none_when_live_and_cache_both_fail(self, db_session):
        with patch.object(
            whatsapp_jobs, "_download_invoice_pdf", return_value=None
        ), patch.object(whatsapp_jobs, "find_cached_invoice_pdf", return_value=None):
            result = whatsapp_jobs._resolve_job_file_path(
                db_session,
                tenant_id=1,
                file_path=None,
                invoice_id="inv-1",
                payment_id=None,
            )
        assert result is None


class TestProcessWhatsappJobSendsTextWithoutPdf:
    """process_whatsapp_job(kind="whatsapp_send") больше не сдаётся, если PDF
    недоступен — текст сообщения (сумма/срок/период) не зависит от вложения,
    так что должник должен получить хотя бы его, а не ничего (см. класс
    выше). Explicit-file jobs (kind="whatsapp_file") — другое дело: там сам
    смысл задачи "отправить именно этот файл", без фолбэка на текст."""

    def test_sends_text_only_when_pdf_unavailable(self, db_session):
        notification = _make_notification(db_session)
        payload = {
            "type": "whatsapp_send",
            "notification_id": notification.id,
            "tenant_id": 1,
            "payment_id": notification.payment_id,
            "invoice_id": "inv-1",
            "counterparty_id": "cp-1",
            "counterparty_name": "ООО Ромашка",
            "service_type": "rent",
        }
        with patch.object(
            whatsapp_jobs, "SessionLocal", return_value=db_session
        ), patch.object(
            whatsapp_jobs, "_resolve_invoice_on_worker", return_value="inv-1"
        ), patch.object(
            whatsapp_jobs, "_resolve_job_file_path", return_value=None
        ), patch.object(
            whatsapp_jobs, "deliver_notification", return_value=True
        ) as deliver_mock, patch.object(
            whatsapp_jobs, "_effective_daily_send_count", return_value=0
        ), patch.object(db_session, "close", lambda: None):
            ok = whatsapp_jobs.process_whatsapp_job(payload)
        assert ok is True
        deliver_mock.assert_called_once()
        assert deliver_mock.call_args.kwargs["file_path"] is None

    def test_whatsapp_file_job_still_fails_without_fallback_to_text(self, db_session):
        """Явная отправка конкретного файла — если файл недоступен, слать
        нечего (в отличие от счёта, у "отправить файл" нет текста-заменителя)."""
        payload = {
            "type": "whatsapp_file",
            "job_id": "job-1",
            "tenant_id": 1,
            "phone_number": "77001234567",
            "message": "текст",
            "file_path": None,
        }
        with patch.object(
            whatsapp_jobs, "SessionLocal", return_value=db_session
        ), patch.object(
            whatsapp_jobs, "_materialize_job_file", return_value=None
        ), patch.object(
            whatsapp_jobs, "_resolve_job_file_path", return_value=None
        ), patch.object(db_session, "close", lambda: None):
            ok = whatsapp_jobs.process_whatsapp_job(payload)
        assert ok is False


class TestDailySendCap:
    """Второй, дневной предохранитель поверх паузы kafka_worker — реальный
    инцидент 2026-09-09 был про скорость (111/минуту), но Green API также
    рекомендует не больше ~200 сообщений/сутки на инстанс для массовых
    рассылок, иначе выглядит как автоматизация."""

    def _make_notification_for_tenant(self, db_session, *, tenant_id: int, sent_at) -> Notification:
        payment = TenantPayment(
            tenant_id=tenant_id,
            ip_name="ИП Тест",
            tenant_name="Арендатор",
            invoice_date=date(2026, 8, 1),
            due_date=date(2026, 8, 25),
            status=PaymentStatus.UNPAID,
            period="2026-08",
        )
        db_session.add(payment)
        db_session.commit()
        notification = Notification(
            payment_id=payment.id,
            notification_type=NotificationType.SAME_DAY,
            status=NotificationStatus.SENT,
            phone_number="77001234567",
            sent_at=sent_at,
        )
        db_session.add(notification)
        db_session.commit()
        return notification

    def test_daily_count_only_counts_todays_notifications_for_this_tenant(
        self, db_session
    ):
        from datetime import datetime, timedelta

        with patch.object(whatsapp_jobs, "astana_today", return_value=date(2026, 9, 10)):
            self._make_notification_for_tenant(
                db_session, tenant_id=1, sent_at=datetime(2026, 9, 10, 8, 0)
            )
            self._make_notification_for_tenant(
                db_session, tenant_id=1, sent_at=datetime(2026, 9, 8, 8, 0)
            )  # другой день — не считается
            self._make_notification_for_tenant(
                db_session, tenant_id=2, sent_at=datetime(2026, 9, 10, 8, 0)
            )  # другой арендатор — не считается

            assert whatsapp_jobs._daily_send_count_for_tenant(db_session, tenant_id=1) == 1

    def test_daily_count_is_zero_without_tenant_id(self, db_session):
        count = whatsapp_jobs._daily_send_count_for_tenant(db_session, tenant_id=None)
        assert count == 0  # tenant_id=None — не блокируем raw-отправки

    def test_job_dropped_and_marked_failed_when_cap_reached(self, db_session):
        notification = _make_notification(db_session)
        payload = {
            "type": "whatsapp_send",
            "notification_id": notification.id,
            "tenant_id": 1,
        }
        with patch.object(
            whatsapp_jobs, "SessionLocal", return_value=db_session
        ), patch.object(
            whatsapp_jobs, "_effective_daily_send_count", return_value=settings.WHATSAPP_DAILY_SEND_CAP
        ), patch.object(
            whatsapp_jobs, "_resolve_invoice_on_worker"
        ) as resolve_mock, patch.object(db_session, "close", lambda: None):
            ok = whatsapp_jobs.process_whatsapp_job(payload)
        db_session.refresh(notification)
        assert ok is True  # не ретраить — лимит не исчезнет в тот же день
        assert notification.status == NotificationStatus.FAILED
        resolve_mock.assert_not_called()  # короткое замыкание до всей остальной работы

    def test_job_proceeds_normally_when_under_cap(self, db_session):
        notification = _make_notification(db_session)
        payload = {
            "type": "whatsapp_send",
            "notification_id": notification.id,
            "tenant_id": 1,
            "invoice_id": "inv-1",
        }
        with patch.object(
            whatsapp_jobs, "SessionLocal", return_value=db_session
        ), patch.object(
            whatsapp_jobs, "_effective_daily_send_count", return_value=0
        ), patch.object(
            whatsapp_jobs, "_resolve_job_file_path", return_value=None
        ), patch.object(
            whatsapp_jobs, "deliver_notification", return_value=True
        ) as deliver_mock, patch.object(db_session, "close", lambda: None):
            ok = whatsapp_jobs.process_whatsapp_job(payload)
        assert ok is True
        deliver_mock.assert_called_once()


class TestEffectiveDailySendCount:
    """2026-09-10: наш собственный дневной счётчик (_daily_send_count_for_tenant)
    видит только отправки из своей БД — слеп к сообщениям, которые менеджер
    шлёт с того же номера вручную (не через приложение). Green API/WhatsApp
    же банят по ОБЩЕМУ трафику номера. _effective_daily_send_count берёт
    максимум из реального счётчика Green API (lastOutgoingMessages, видит и
    ручные тоже) и своего — и падает на свой, если Green API недоступен."""

    def test_uses_real_green_api_count_when_higher_than_own(self, db_session):
        with patch.object(
            whatsapp_jobs, "_daily_send_count_for_tenant", return_value=3
        ), patch.object(whatsapp_jobs, "get_whatsapp_for_tenant") as get_wa_mock:
            get_wa_mock.return_value.get_today_outgoing_count.return_value = 42
            count = whatsapp_jobs._effective_daily_send_count(db_session, tenant_id=1)
        assert count == 42

    def test_falls_back_to_own_count_when_green_api_unavailable(self, db_session):
        with patch.object(
            whatsapp_jobs, "_daily_send_count_for_tenant", return_value=3
        ), patch.object(whatsapp_jobs, "get_whatsapp_for_tenant") as get_wa_mock:
            get_wa_mock.return_value.get_today_outgoing_count.return_value = None
            count = whatsapp_jobs._effective_daily_send_count(db_session, tenant_id=1)
        assert count == 3

    def test_never_undercounts_relative_to_own_db(self, db_session):
        """Защита от гипотетической рассинхронизации (например, только что
        отправленное сообщение ещё не попало в ответ lastOutgoingMessages) —
        эффективный счётчик не должен быть НИЖЕ того, что мы точно знаем
        из своей БД."""
        with patch.object(
            whatsapp_jobs, "_daily_send_count_for_tenant", return_value=50
        ), patch.object(whatsapp_jobs, "get_whatsapp_for_tenant") as get_wa_mock:
            get_wa_mock.return_value.get_today_outgoing_count.return_value = 10
            count = whatsapp_jobs._effective_daily_send_count(db_session, tenant_id=1)
        assert count == 50


class TestGetTodayOutgoingCount:
    """WhatsAppService.get_today_outgoing_count — обёртка над Green API
    lastOutgoingMessages, считает ВСЕ исходящие сегодня (по Astana),
    включая sendByApi=false (ручные)."""

    def _service(self) -> WhatsAppService:
        return WhatsAppService(id_instance="123", api_token="tok")

    def test_counts_all_items_regardless_of_send_by_api(self):
        from datetime import datetime
        from unittest.mock import MagicMock
        from app.services.auto_notification_service import astana_now

        today_ts = int(astana_now().replace(hour=10, minute=0, second=0, microsecond=0).timestamp())
        fake_response = MagicMock(status_code=200)
        fake_response.json.return_value = [
            {"idMessage": "1", "timestamp": today_ts, "sendByApi": True},
            {"idMessage": "2", "timestamp": today_ts, "sendByApi": False},
        ]
        with patch("app.services.whatsapp_service.requests.get", return_value=fake_response):
            count = self._service().get_today_outgoing_count()
        assert count == 2

    def test_excludes_items_from_before_todays_midnight(self):
        from unittest.mock import MagicMock
        from datetime import timedelta
        from app.services.auto_notification_service import astana_now

        yesterday_ts = int((astana_now() - timedelta(days=1)).timestamp())
        fake_response = MagicMock(status_code=200)
        fake_response.json.return_value = [
            {"idMessage": "1", "timestamp": yesterday_ts, "sendByApi": False},
        ]
        with patch("app.services.whatsapp_service.requests.get", return_value=fake_response):
            count = self._service().get_today_outgoing_count()
        assert count == 0

    def test_returns_none_on_non_200_response(self):
        from unittest.mock import MagicMock

        fake_response = MagicMock(status_code=500, text="boom")
        with patch("app.services.whatsapp_service.requests.get", return_value=fake_response):
            count = self._service().get_today_outgoing_count()
        assert count is None

    def test_returns_none_on_request_exception(self):
        with patch("app.services.whatsapp_service.requests.get", side_effect=Exception("network down")):
            count = self._service().get_today_outgoing_count()
        assert count is None

    def test_returns_none_when_not_configured(self):
        service = WhatsAppService(id_instance=None, api_token=None)
        assert service.get_today_outgoing_count() is None


class TestProcessGreenApiWebhook:
    """Раньше process_webhook_job для source="green-api" был заглушкой —
    ничего не сохранял. См. deliver_notification: успех больше не значит
    DELIVERED, только этот вебхук может подтвердить реальную доставку."""

    def _webhook_payload(self, *, id_message: str, status: str) -> dict:
        return {
            "source": "green-api",
            "job_id": "job-1",
            "body": {
                "typeWebhook": "outgoingMessageStatus",
                "idMessage": id_message,
                "status": status,
            },
        }

    def test_delivered_status_marks_notification_delivered(self, db_session):
        notification = _make_notification(db_session)
        notification.green_api_id_message = "msg-1"
        db_session.commit()

        with patch.object(whatsapp_jobs, "SessionLocal", return_value=db_session), patch.object(
            db_session, "close", lambda: None
        ):
            whatsapp_jobs.process_webhook_job(
                self._webhook_payload(id_message="msg-1", status="delivered")
            )
        db_session.refresh(notification)
        assert notification.status == NotificationStatus.DELIVERED
        assert notification.delivered_at is not None

    def test_read_status_also_marks_delivered(self, db_session):
        notification = _make_notification(db_session)
        notification.green_api_id_message = "msg-2"
        db_session.commit()

        with patch.object(whatsapp_jobs, "SessionLocal", return_value=db_session), patch.object(
            db_session, "close", lambda: None
        ):
            whatsapp_jobs.process_webhook_job(
                self._webhook_payload(id_message="msg-2", status="read")
            )
        db_session.refresh(notification)
        assert notification.status == NotificationStatus.DELIVERED

    @pytest.mark.parametrize(
        "wa_status", ["failed", "noAccount", "suspended", "notInGroup"]
    )
    def test_failure_statuses_mark_notification_failed(self, db_session, wa_status):
        """suspended — ровно то, что случилось 2026-09-09: sendMessage вернул
        200, но инстанс уже был заблокирован WhatsApp."""
        notification = _make_notification(db_session)
        notification.green_api_id_message = "msg-3"
        db_session.commit()

        with patch.object(whatsapp_jobs, "SessionLocal", return_value=db_session), patch.object(
            db_session, "close", lambda: None
        ):
            whatsapp_jobs.process_webhook_job(
                self._webhook_payload(id_message="msg-3", status=wa_status)
            )
        db_session.refresh(notification)
        assert notification.status == NotificationStatus.FAILED

    def test_unknown_id_message_is_a_noop(self, db_session):
        notification = _make_notification(db_session)
        notification.green_api_id_message = "msg-4"
        db_session.commit()

        with patch.object(whatsapp_jobs, "SessionLocal", return_value=db_session), patch.object(
            db_session, "close", lambda: None
        ):
            whatsapp_jobs.process_webhook_job(
                self._webhook_payload(id_message="does-not-exist", status="delivered")
            )
        db_session.refresh(notification)
        assert notification.status == NotificationStatus.SENT

    def test_non_green_api_source_is_ignored(self, db_session):
        with patch.object(whatsapp_jobs, "SessionLocal", return_value=db_session):
            whatsapp_jobs.process_webhook_job({"source": "other", "body": {}})
        # не должно бросить исключение и не должно трогать SessionLocal-сессию

    def test_sent_status_is_a_noop(self, db_session):
        """"sent" — промежуточный статус, дальше либо delivered, либо failed;
        значение по умолчанию (SENT) и так уже проставлено."""
        notification = _make_notification(db_session)
        notification.green_api_id_message = "msg-5"
        db_session.commit()

        with patch.object(whatsapp_jobs, "SessionLocal", return_value=db_session), patch.object(
            db_session, "close", lambda: None
        ):
            whatsapp_jobs.process_webhook_job(
                self._webhook_payload(id_message="msg-5", status="sent")
            )
        db_session.refresh(notification)
        assert notification.status == NotificationStatus.SENT


class TestKafkaWorkerRequeue:
    def test_gives_up_after_max_retries_without_looping_forever(self):
        from app.workers.kafka_worker import MAX_WHATSAPP_JOB_RETRIES, _requeue_whatsapp_job

        with patch(
            "app.services.job_queue.enqueue_whatsapp_job"
        ) as enqueue:
            _requeue_whatsapp_job({"notification_id": 1, "_retry_count": MAX_WHATSAPP_JOB_RETRIES})
            enqueue.assert_not_called()

    def test_requeues_with_incremented_retry_count(self):
        from app.workers.kafka_worker import _requeue_whatsapp_job

        with patch("app.services.job_queue.enqueue_whatsapp_job", return_value=True) as enqueue:
            _requeue_whatsapp_job({"notification_id": 1, "_retry_count": 1})
            assert enqueue.call_count == 1
            sent_payload = enqueue.call_args[0][0]
            assert sent_payload["_retry_count"] == 2


class TestKafkaWorkerPacing:
    """Реальный инцидент 2026-09-09: 111 WhatsApp-отправок ушли за одну
    минуту (max_records=10 на poll(), без паузы вообще) — инстанс словил
    временную блокировку, 104 из 111 счетов не дошли. Пауза должна
    срабатывать после КАЖДОГО whatsapp-сообщения независимо от исхода
    (успех/неуспех/исключение), и только для whatsapp-топика."""

    def _make_message(self, topic: str, value: dict):
        return type(
            "Msg",
            (),
            {"topic": topic, "value": value, "partition": 0, "offset": 1, "key": None},
        )()

    def test_paces_after_successful_whatsapp_send(self):
        from app.workers import kafka_worker

        consumer = type("Consumer", (), {"commit": lambda self: None})()
        message = self._make_message(kafka_worker.settings.KAFKA_TOPIC_WHATSAPP, {"job_id": "1"})
        with patch.object(
            kafka_worker, "process_whatsapp_job", return_value=True
        ), patch.object(kafka_worker, "_paced_sleep") as sleep_mock:
            kafka_worker._process_message(consumer, message)
        sleep_mock.assert_called_once_with(kafka_worker.settings.WHATSAPP_SEND_DELAY_SECONDS)

    def test_paces_after_failed_whatsapp_send_too(self):
        """Раньше пауза случайно оказывалась внутри except-блока — на успешном
        пути (return True, без исключения) она бы вообще не срабатывала.
        Пауза — про ограничение исходящего трафика на инстанс, а не про
        реакцию на конкретный исход одной задачи."""
        from app.workers import kafka_worker

        consumer = type("Consumer", (), {"commit": lambda self: None})()
        message = self._make_message(kafka_worker.settings.KAFKA_TOPIC_WHATSAPP, {"job_id": "1"})
        with patch.object(
            kafka_worker, "process_whatsapp_job", return_value=False
        ), patch.object(kafka_worker, "_requeue_whatsapp_job"), patch.object(
            kafka_worker, "_paced_sleep"
        ) as sleep_mock:
            kafka_worker._process_message(consumer, message)
        sleep_mock.assert_called_once_with(kafka_worker.settings.WHATSAPP_SEND_DELAY_SECONDS)

    def test_paces_even_when_job_raises(self):
        from app.workers import kafka_worker

        consumer = type("Consumer", (), {"commit": lambda self: None})()
        message = self._make_message(kafka_worker.settings.KAFKA_TOPIC_WHATSAPP, {"job_id": "1"})
        with patch.object(
            kafka_worker, "process_whatsapp_job", side_effect=RuntimeError("boom")
        ), patch.object(kafka_worker, "_requeue_whatsapp_job"), patch.object(
            kafka_worker, "_paced_sleep"
        ) as sleep_mock:
            kafka_worker._process_message(consumer, message)
        sleep_mock.assert_called_once_with(kafka_worker.settings.WHATSAPP_SEND_DELAY_SECONDS)

    def test_does_not_pace_other_topics(self):
        from app.workers import kafka_worker

        consumer = type("Consumer", (), {"commit": lambda self: None})()
        message = self._make_message(kafka_worker.settings.KAFKA_TOPIC_WEBHOOK, {"job_id": "1"})
        with patch.object(kafka_worker, "process_webhook_job"), patch.object(
            kafka_worker, "_paced_sleep"
        ) as sleep_mock:
            kafka_worker._process_message(consumer, message)
        sleep_mock.assert_not_called()

    def test_paced_sleep_stops_early_on_shutdown(self):
        from app.workers import kafka_worker

        kafka_worker._shutdown_requested = True
        try:
            with patch.object(kafka_worker.time, "sleep") as time_sleep:
                kafka_worker._paced_sleep(45)
            time_sleep.assert_not_called()
        finally:
            kafka_worker._shutdown_requested = False

    def test_paced_sleep_sleeps_in_one_second_increments(self):
        from app.workers import kafka_worker

        with patch.object(kafka_worker.time, "sleep") as time_sleep:
            kafka_worker._paced_sleep(3)
        assert time_sleep.call_count == 3
        assert all(call.args[0] == 1.0 for call in time_sleep.call_args_list)
