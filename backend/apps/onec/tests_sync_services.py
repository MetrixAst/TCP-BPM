from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from finances.models import CashFlowRecord, GeneratedInvoice, TenantPaymentRegistry
from onec.services.sync_cashflow import sync_cashflow_from_1c, upsert_payment
from onec.services.sync_invoices import sync_generated_invoices_from_1c
from tenants.models import Tenant
from finances.tests import make_tenant


@override_settings(
    ONE_C_BASE_URL='https://1c.example/api/v1',
    ONE_C_API_USER='u',
    ONE_C_API_PASSWORD='p',
    ONE_C_BASIC_AUTH_USER='b',
    ONE_C_BASIC_AUTH_PASSWORD='b',
)
class OneCSyncServicesTest(TestCase):

    def test_upsert_payment_creates_cashflow(self):
        upsert_payment({
            'id': 'pay-001',
            'type': 'incoming',
            'amount': 50000,
            'currency': 'KZT',
            'date': '2026-05-20',
            'purpose': 'Аренда',
            'number': 'P-1',
        })
        rec = CashFlowRecord.objects.get(onec_id='pay-001')
        self.assertEqual(rec.direction, CashFlowRecord.Direction.INFLOW)
        self.assertEqual(rec.amount, Decimal('50000'))

    @patch('onec.services.sync_cashflow.get_onec_client')
    def test_sync_cashflow_from_client(self, mock_client_factory):
        payment = MagicMock()
        payment.id = 'pay-002'
        payment.type = 'outgoing'
        payment.amount = 1000
        payment.currency = 'KZT'
        payment.date = '2026-05-21'
        payment.purpose = 'Test'
        payment.number = '2'
        payment.counterparty_id = ''

        client = MagicMock()
        client.get_payments.return_value = [payment]
        mock_client_factory.return_value = client

        result = sync_cashflow_from_1c()
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(CashFlowRecord.objects.filter(onec_id='pay-002').exists())

    @patch('onec.services.sync_invoices.get_onec_client')
    def test_sync_invoice_status(self, mock_client_factory):
        tenant = make_tenant('SyncInv')
        inv = GeneratedInvoice.objects.create(
            tenant=tenant,
            number='СЧ-SYNC-1',
            total_amount=Decimal('100000'),
            status=GeneratedInvoice.Status.SENT,
        )
        onec_inv = MagicMock()
        onec_inv.id = '1c-inv-99'
        onec_inv.number = 'СЧ-SYNC-1'
        onec_inv.amount = 100000
        onec_inv.status = 'paid'
        onec_inv.counterparty_id = ''
        onec_inv.paid_amount = 100000

        client = MagicMock()
        client.get_invoices.return_value = [onec_inv]
        mock_client_factory.return_value = client

        result = sync_generated_invoices_from_1c()
        self.assertEqual(result['status'], 'ok')
        inv.refresh_from_db()
        self.assertEqual(inv.onec_id, '1c-inv-99')
        self.assertEqual(inv.status, GeneratedInvoice.Status.PAID)
