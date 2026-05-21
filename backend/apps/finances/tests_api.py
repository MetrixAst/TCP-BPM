from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import UserAccount
from account.role_permissions import RoleEnums
from .models import TenantPaymentRegistry, PaymentCalendarEntry, GeneratedInvoice, BudgetCategory, BudgetItem
from .tests import make_tenant


class FinanceAPITestCase(APITestCase):
    def setUp(self):
        self.tenant = make_tenant()
        self.cfo = UserAccount.objects.create_user(
            username='api_cfo',
            password='pass',
            role=RoleEnums.CFO.value,
        )
        self.accountant = UserAccount.objects.create_user(
            username='api_accountant',
            password='pass',
            role=RoleEnums.CHIEF_ACCOUNTANT.value,
        )
        self.staff = UserAccount.objects.create_user(
            username='api_staff_fin',
            password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.payment = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-API',
            period=date(2026, 5, 1),
            charged=Decimal('100000'),
            paid=Decimal('50000'),
        )
        self.calendar_entry = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-API',
            expected_date=date(2026, 5, 15),
            expected_amount=Decimal('50000'),
        )
        self.category = BudgetCategory.objects.create(
            name='Аренда',
            category_type=BudgetCategory.Type.EXPENSE,
            code='RENT',
        )
        self.budget_item = BudgetItem.objects.create(
            category=self.category,
            year=2026,
            month=5,
            plan=Decimal('100000'),
        )
        self.invoice = GeneratedInvoice.objects.create(
            tenant=self.tenant,
            number='INV-API-001',
            total_amount=Decimal('50000'),
        )
        self.payments_url = reverse('finance-payment-list')
        self.calendar_url = reverse('finance-calendar-list')
        self.invoices_url = reverse('finance-invoice-list')
        self.budget_url = reverse('finance-budget-list')

    def test_payments_unauthenticated_401(self):
        response = self.client.get(self.payments_url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_payments_staff_403(self):
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(
            self.client.get(self.payments_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_payments_list_cfo_200(self):
        self.client.force_authenticate(user=self.cfo)
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)

    def test_payments_retrieve(self):
        self.client.force_authenticate(user=self.cfo)
        url = reverse('finance-payment-detail', kwargs={'pk': self.payment.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['contract_number'], 'ДОГ-API')

    def test_calendar_readonly_no_post(self):
        self.client.force_authenticate(user=self.cfo)
        response = self.client.post(self.calendar_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_calendar_list(self):
        self.client.force_authenticate(user=self.accountant)
        response = self.client.get(self.calendar_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invoice_create(self):
        self.client.force_authenticate(user=self.cfo)
        payload = {
            'tenant': self.tenant.id,
            'number': 'INV-NEW',
            'total_amount': '75000.00',
            'items': [
                {'name': 'Аренда', 'quantity': '1', 'price': '75000.00'},
            ],
        }
        response = self.client.post(self.invoices_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(GeneratedInvoice.objects.filter(number='INV-NEW').count(), 1)

    def test_budget_read_accountant(self):
        self.client.force_authenticate(user=self.accountant)
        response = self.client.get(reverse('finance-budget-detail', kwargs={'pk': self.budget_item.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_budget_write_accountant_403(self):
        self.client.force_authenticate(user=self.accountant)
        payload = {
            'category': self.category.id,
            'year': 2026,
            'month': 6,
            'plan': '5000.00',
            'period_type': 'monthly',
        }
        response = self.client.post(self.budget_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_budget_write_cfo_201(self):
        self.client.force_authenticate(user=self.cfo)
        payload = {
            'category': self.category.id,
            'year': 2027,
            'month': 3,
            'plan': '8000.00',
            'fact': '0.00',
            'forecast': '0.00',
            'period_type': 'monthly',
        }
        response = self.client.post(self.budget_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
