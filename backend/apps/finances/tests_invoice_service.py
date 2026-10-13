from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from account.models import UserAccount
from finances.models import GeneratedInvoice, InvoiceSyncRun, PaymentCalendarEntry, TenantPaymentRegistry
from finances.services.invoice_sync import normalize_name, recent_periods, sync_invoices_from_service
from onec.models import Counterparty
from tenants.models import Tenant

SERVICE = dict(
    INVOICE_SERVICE_URL='https://invoice.test', INVOICE_SERVICE_USERNAME='trc', INVOICE_SERVICE_PASSWORD='x',
    INVOICE_SERVICE_SYNC_MONTHS=1, INVOICE_SERVICE_TENANT_IDS='',
)


class FakeClient:
    """Отдаёт счета и оплаты в формате invoice-сервиса."""

    def __init__(self, invoices, payments):
        self.invoices, self.payments = invoices, payments
        self.sent = []

    def list_invoices(self, period, tenant_id=None):
        return self.invoices

    def list_payments(self, period, tenant_id=None):
        return self.payments

    def send_whatsapp(self, **kwargs):
        self.sent.append(('whatsapp', kwargs))
        return {'id': 1}

    def send_email(self, **kwargs):
        self.sent.append(('email', kwargs))
        return {'ok': True, 'email': 'shop@example.kz'}

    def download_invoice_pdf(self, invoice_id, counterparty_id, tenant_id=None):
        return b'%PDF-1.4 from-1c'


def invoice_row(guid, number, cp_id, cp_name, amount, bin_value=''):
    return {
        'id': guid, 'number': number, 'date': str(timezone.localdate()), 'status': 'posted',
        'counterparty_id': cp_id, 'counterparty_name': cp_name,
        'counterparty': {'id': cp_id, 'name': cp_name, 'bin': bin_value},
        'amount': amount, 'vat': 0,
        'items': [{'name': 'Аренда помещения', 'quantity': 1, 'price': amount, 'amount': amount}],
    }


def payment_row(guid, amount, status, due, paid_amount=None, paid_at=None):
    return {
        'id': 77, 'invoice_id': guid, 'amount': amount, 'paid_amount': paid_amount, 'status': status,
        'due_date': str(due), 'paid_at': paid_at, 'service_type': 'rent', 'notifications': [],
    }


@override_settings(**SERVICE)
class InvoiceSyncTest(TestCase):
    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()
        self.coffee = Tenant.objects.create(name='Кофейня', area=40, price=5000, phone='', email='', address='', contact='')

    def _client(self, status='unpaid', paid_amount=None, paid_at=None, due=None):
        due = due or self.today + timedelta(days=5)
        return FakeClient(
            invoices=[
                invoice_row('inv-1', '0001', 'cp-1', 'ТОО «Кофейня»', 300000, '111111111111'),
                invoice_row('inv-2', '0002', 'cp-2', 'ИП Неизвестный', 100000),
            ],
            payments=[
                payment_row('inv-1', 300000, status, due, paid_amount, paid_at),
                payment_row('inv-2', 100000, 'unpaid', due),
            ],
        )

    def test_invoices_land_in_registry_calendar_and_invoices(self):
        run = sync_invoices_from_service(client=self._client(), trigger='manual')

        self.assertEqual(run.status, InvoiceSyncRun.Status.PARTIAL)
        self.assertEqual(run.stats['invoices'], 2)
        self.assertEqual(run.stats['registry'], 1)
        self.assertEqual([u['name'] for u in run.unmatched], ['ИП Неизвестный'])

        invoice = GeneratedInvoice.objects.get(onec_id='inv-1')
        self.assertEqual(invoice.tenant, self.coffee)
        self.assertEqual(invoice.total_amount, Decimal('300000.00'))
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(invoice.counterparty.bin_number, '111111111111')

        registry = TenantPaymentRegistry.objects.get(onec_id='inv:inv-1')
        self.assertEqual(registry.balance, Decimal('300000.00'))
        self.assertEqual(registry.status, TenantPaymentRegistry.Status.PENDING)
        calendar = PaymentCalendarEntry.objects.get(onec_id='inv:inv-1')
        self.assertEqual(calendar.status, PaymentCalendarEntry.Status.PLAN)

        self.assertIsNone(GeneratedInvoice.objects.get(onec_id='inv-2').tenant)
        self.assertFalse(TenantPaymentRegistry.objects.filter(onec_id='inv:inv-2').exists())

    def test_payment_from_1c_closes_debt(self):
        sync_invoices_from_service(client=self._client())
        paid_at = (timezone.now() - timedelta(days=1)).isoformat()
        sync_invoices_from_service(client=self._client(status='paid', paid_amount=300000, paid_at=paid_at))

        self.assertEqual(GeneratedInvoice.objects.get(onec_id='inv-1').status, GeneratedInvoice.Status.PAID)
        registry = TenantPaymentRegistry.objects.get(onec_id='inv:inv-1')
        self.assertEqual(registry.status, TenantPaymentRegistry.Status.PAID)
        self.assertEqual(registry.balance, Decimal('0.00'))
        self.assertEqual(PaymentCalendarEntry.objects.get(onec_id='inv:inv-1').status, PaymentCalendarEntry.Status.FACT)
        self.assertEqual(TenantPaymentRegistry.objects.count(), 1)

    def test_overdue_marked(self):
        sync_invoices_from_service(client=self._client(due=self.today - timedelta(days=10)))
        registry = TenantPaymentRegistry.objects.get(onec_id='inv:inv-1')
        self.assertEqual(registry.status, TenantPaymentRegistry.Status.OVERDUE)
        self.assertEqual(registry.overdue_days, 10)

    def test_link_unmatched_counterparty(self):
        sync_invoices_from_service(client=self._client())
        other = Tenant.objects.create(name='Магазин 5', area=10, price=1, phone='', email='', address='', contact='')
        admin = UserAccount.objects.create_user(username='fin_admin', password='x', role='administrator')
        self.client.force_login(admin)
        self.client.post(reverse('finances:sync_link'), {'onec_id': 'cp-2', 'tenant': other.pk})
        other.refresh_from_db()
        self.assertEqual(other.counterparty.id_1c, 'cp-2')

        run = sync_invoices_from_service(client=self._client())
        self.assertEqual(run.unmatched, [])
        self.assertEqual(TenantPaymentRegistry.objects.get(onec_id='inv:inv-2').tenant, other)

    def test_helpers(self):
        self.assertEqual(normalize_name('ТОО «Кофейня»'), 'кофейня')
        self.assertEqual(len(recent_periods(3)), 3)


@override_settings(**SERVICE)
class InvoiceSendTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = UserAccount.objects.create_user(username='inv_admin', password='x', role='administrator')
        self.client.force_login(self.admin)
        self.fake = FakeClient([], [])
        cp = Counterparty.objects.create(id_1c='cp-9', full_name='ТОО Бутик', short_name='Бутик', phone='+77010000000')
        self.invoice = GeneratedInvoice.objects.create(
            number='0009', onec_id='inv-9', counterparty=cp, counterparty_onec_id='cp-9',
            counterparty_name='ТОО Бутик', total_amount=1000,
        )

    def _post(self, data):
        with mock.patch('finances.services.invoice_service.InvoiceServiceClient', return_value=self.fake):
            return self.client.post(reverse('finances:invoice_send', args=[self.invoice.pk]), data)

    def test_send_whatsapp(self):
        self._post({'sent_via': 'whatsapp', 'phone': '+7 701 000 00 00'})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, GeneratedInvoice.Status.SENT)
        self.assertEqual(self.invoice.sent_via, 'whatsapp')
        channel, kwargs = self.fake.sent[0]
        self.assertEqual(kwargs['phone'], '+77010000000')
        self.assertEqual(kwargs['invoice_id'], 'inv-9')

    def test_send_email(self):
        self._post({'sent_via': 'email', 'email': ''})
        self.assertEqual(self.fake.sent[0][0], 'email')

    def test_manual_paid_blocked_and_delete_blocked(self):
        self.invoice.status = GeneratedInvoice.Status.SENT
        self.invoice.save()
        self.client.post(reverse('finances:invoice_mark_paid', args=[self.invoice.pk]))
        self.client.post(reverse('finances:invoice_delete', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, GeneratedInvoice.Status.SENT)

    def test_pdf_from_service(self):
        with mock.patch('finances.services.invoice_service.InvoiceServiceClient', return_value=self.fake):
            response = self.client.get(reverse('finances:invoice_pdf', args=[self.invoice.pk]))
        self.assertEqual(response.content, b'%PDF-1.4 from-1c')

    def test_sync_page_renders(self):
        sync_invoices_from_service(client=FakeClient([invoice_row('a', '1', 'cp-x', 'Кто-то', 10)], []))
        response = self.client.get(reverse('finances:sync_status'))
        self.assertContains(response, 'Кто-то')
