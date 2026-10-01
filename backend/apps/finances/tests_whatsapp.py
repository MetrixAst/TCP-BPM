from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings

from account.models import UserAccount
from finances.models import GeneratedInvoice
from finances.services import invoice_service
from finances.services.notifications import _resolve_recipient_phone, send_invoice_via_whatsapp
from onec.models import Counterparty

from .tests import make_tenant

SERVICE = dict(
    INVOICE_SERVICE_URL='http://invoice.test',
    INVOICE_SERVICE_USERNAME='bpm',
    INVOICE_SERVICE_PASSWORD='secret',
    INVOICE_SERVICE_TENANT_ID=7,
    INVOICE_SERVICE_TIMEOUT=5,
)


def _resp(status, body):
    resp = MagicMock(status_code=status)
    resp.json.return_value = body
    return resp


def _invoice(counterparty=None, tenant=None, **kwargs):
    return GeneratedInvoice.objects.create(
        number='WA-001', total_amount=Decimal('1000'), counterparty=counterparty, tenant=tenant, **kwargs
    )


def _counterparty(phone='+7 701 111 22 33'):
    return Counterparty.objects.create(
        id_1c='cp-guid-1', full_name='ТОО Ромашка', short_name='Ромашка', phone=phone
    )


@override_settings(**SERVICE)
class InvoiceServiceClientTest(TestCase):
    def setUp(self):
        cache.delete(invoice_service.TOKEN_CACHE_KEY)

    @patch('finances.services.invoice_service.requests.request')
    @patch('finances.services.invoice_service.requests.post')
    def test_sends_file_with_tenant_and_counterparty(self, post, request):
        post.return_value = _resp(200, {'access_token': 'tok'})
        request.return_value = _resp(200, {'success': True})

        invoice_service.send_file_via_whatsapp(
            phone='+77011112233', counterparty_id='cp-1', file_name='a.pdf', file_bytes=b'%PDF',
        )

        method, url = request.call_args.args
        self.assertEqual((method, url), ('POST', 'http://invoice.test/api/notifications/send-file'))
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs['headers'], {'Authorization': 'Bearer tok'})
        self.assertEqual(kwargs['data']['tenant_id'], '7')
        self.assertEqual(kwargs['data']['counterparty_id'], 'cp-1')
        self.assertNotIn('invoice_id', kwargs['data'])

    @patch('finances.services.invoice_service.requests.request')
    @patch('finances.services.invoice_service.requests.post')
    def test_token_is_cached(self, post, request):
        post.return_value = _resp(200, {'access_token': 'tok'})
        request.return_value = _resp(200, {'success': True})
        for _ in range(2):
            invoice_service.send_file_via_whatsapp(
                phone='1', counterparty_id='cp', file_name='a.pdf', file_bytes=b'',
            )
        self.assertEqual(post.call_count, 1)

    @patch('finances.services.invoice_service.requests.request')
    @patch('finances.services.invoice_service.requests.post')
    def test_relogin_on_expired_token(self, post, request):
        cache.set(invoice_service.TOKEN_CACHE_KEY, 'old')
        post.return_value = _resp(200, {'access_token': 'new'})
        request.side_effect = [_resp(401, {'detail': 'expired'}), _resp(200, {'success': True})]

        invoice_service.send_file_via_whatsapp(
            phone='1', counterparty_id='cp', file_name='a.pdf', file_bytes=b'',
        )
        self.assertEqual(request.call_args.kwargs['headers'], {'Authorization': 'Bearer new'})

    @patch('finances.services.invoice_service.requests.request')
    @patch('finances.services.invoice_service.requests.post')
    def test_service_rejection_raises_with_detail(self, post, request):
        post.return_value = _resp(200, {'access_token': 'tok'})
        request.return_value = _resp(403, {'detail': 'Номер не совпадает с телефоном этого контрагента в 1С'})
        with self.assertRaisesMessage(invoice_service.InvoiceServiceError, 'Номер не совпадает'):
            invoice_service.send_file_via_whatsapp(
                phone='1', counterparty_id='cp', file_name='a.pdf', file_bytes=b'',
            )

    @patch('finances.services.invoice_service.requests.post', side_effect=requests.ConnectionError)
    def test_unreachable_service_raises(self, post):
        with self.assertRaisesMessage(invoice_service.InvoiceServiceError, 'недоступен'):
            invoice_service.send_file_via_whatsapp(
                phone='1', counterparty_id='cp', file_name='a.pdf', file_bytes=b'',
            )

    @override_settings(INVOICE_SERVICE_URL='')
    def test_not_configured_without_url(self):
        self.assertFalse(invoice_service.is_configured())


@override_settings(**SERVICE)
@patch('finances.services.invoice_pdf.build_invoice_pdf', return_value=b'%PDF-test')
class SendInvoiceViaWhatsAppTest(TestCase):
    @patch('finances.services.invoice_service.send_file_via_whatsapp')
    def test_success_marks_sent(self, send, _pdf):
        invoice = _invoice(counterparty=_counterparty(), onec_id='inv-guid')

        ok, _msg = send_invoice_via_whatsapp(invoice)

        self.assertTrue(ok)
        send.assert_called_once_with(
            phone='+7 701 111 22 33', counterparty_id='cp-guid-1',
            file_name=f'invoice_{invoice.pk}.pdf', file_bytes=b'%PDF-test', invoice_number='inv-guid',
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, GeneratedInvoice.Status.SENT)
        self.assertEqual(invoice.sent_via, GeneratedInvoice.SentVia.WHATSAPP)
        self.assertIsNotNone(invoice.sent_at)

    @patch('finances.services.invoice_service.send_file_via_whatsapp',
           side_effect=invoice_service.InvoiceServiceError('Сервис счетов недоступен'))
    def test_failure_keeps_created(self, _send, _pdf):
        invoice = _invoice(counterparty=_counterparty())

        ok, msg = send_invoice_via_whatsapp(invoice)

        self.assertFalse(ok)
        self.assertEqual(msg, 'Сервис счетов недоступен')
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, GeneratedInvoice.Status.CREATED)
        self.assertIsNone(invoice.sent_at)

    @patch('finances.services.invoice_service.send_file_via_whatsapp')
    def test_requires_counterparty_from_1c(self, send, _pdf):
        ok, msg = send_invoice_via_whatsapp(_invoice(tenant=make_tenant('wa_tenant')))
        self.assertFalse(ok)
        self.assertIn('1С', msg)
        send.assert_not_called()

    @patch('finances.services.invoice_service.send_file_via_whatsapp')
    def test_requires_phone(self, send, _pdf):
        ok, msg = send_invoice_via_whatsapp(_invoice(counterparty=_counterparty(phone='')))
        self.assertFalse(ok)
        self.assertIn('телефон', msg)
        send.assert_not_called()

    @override_settings(INVOICE_SERVICE_TENANT_ID=0)
    @patch('finances.services.invoice_service.send_file_via_whatsapp')
    def test_not_configured(self, send, _pdf):
        ok, msg = send_invoice_via_whatsapp(_invoice(counterparty=_counterparty()))
        self.assertFalse(ok)
        self.assertIn('не настроен', msg)
        send.assert_not_called()


class ResolveRecipientPhoneTest(TestCase):
    def test_first_of_several_counterparty_phones(self):
        invoice = _invoice(counterparty=_counterparty(phone='87011112233, 87770001122'))
        self.assertEqual(_resolve_recipient_phone(invoice), '87011112233')

    def test_falls_back_to_tenant_phone(self):
        invoice = _invoice(counterparty=_counterparty(phone=''), tenant=make_tenant('wa_fallback'))
        self.assertEqual(_resolve_recipient_phone(invoice), '+77001234567')

    def test_none_without_phones(self):
        self.assertIsNone(_resolve_recipient_phone(_invoice()))


@override_settings(**SERVICE)
class InvoiceSendWhatsAppViewTest(TestCase):
    def setUp(self):
        UserAccount.objects.create_user(
            username='wa_user', password='pass', role='administrator', is_superuser=True
        )
        self.client.login(username='wa_user', password='pass')
        self.invoice = _invoice(counterparty=_counterparty())
        self.url = f'/finances/invoices/{self.invoice.pk}/send/'

    @patch('finances.services.notifications.send_invoice_via_whatsapp', return_value=(True, 'ok'))
    def test_whatsapp_branch_calls_service(self, send):
        self.client.post(self.url, {'sent_via': 'whatsapp'})
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0].pk, self.invoice.pk)

    @patch('finances.services.notifications.send_invoice_via_whatsapp',
           return_value=(False, 'Номер не совпадает'))
    def test_whatsapp_failure_shows_error_and_keeps_status(self, _send):
        resp = self.client.post(self.url, {'sent_via': 'whatsapp'}, follow=True)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, GeneratedInvoice.Status.CREATED)
        self.assertContains(resp, 'Номер не совпадает')

    def test_detail_shows_whatsapp_option_when_configured(self):
        resp = self.client.get(f'/finances/invoices/{self.invoice.pk}/')
        self.assertContains(resp, 'value="whatsapp"')

    @override_settings(INVOICE_SERVICE_URL='')
    def test_detail_hides_whatsapp_option_when_not_configured(self):
        resp = self.client.get(f'/finances/invoices/{self.invoice.pk}/')
        self.assertNotContains(resp, 'value="whatsapp"')
