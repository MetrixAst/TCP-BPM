from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from account.models import UserAccount
from account.role_permissions import MenuItem
from finances.models import (
    BudgetItem, CashFlowRecord, CreditModel, FinancialStatement, GeneratedInvoice,
    PaymentCalendarEntry, TenantPaymentRegistry,
)
from tenants.models import Tenant

PAGES = [
    'finances:dashboard', 'finances:reg', 'finances:payment_calendar', 'finances:invoice_list',
    'finances:opiu', 'finances:cashflow', 'finances:budget_list', 'finances:credit_model_list',
    'finances:rent_analytics', 'finances:dashboard_kpi', 'finances:dashboard_balances',
    'finances:cashflow_daily', 'finances:cashflow_weekly', 'finances:cashflow_forecast',
]


@override_settings(FINANCES_MENU_ENABLED=True)
class FinanceDemoSeedTest(TestCase):

    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            username='fin_demo_admin', password='pass', role='administrator',
        )

    def test_seed_fills_every_block_and_is_repeatable(self):
        call_command('seed_finance_demo', verbosity=0)
        call_command('seed_finance_demo', verbosity=0)

        self.assertEqual(Tenant.objects.filter(note='DEMO').count(), 8)
        self.assertEqual(TenantPaymentRegistry.objects.count(), 8 * 12)
        self.assertTrue(TenantPaymentRegistry.objects.filter(status='overdue').exists())
        self.assertEqual(PaymentCalendarEntry.objects.count(), 8 * 6)
        self.assertEqual(GeneratedInvoice.objects.count(), 16)
        self.assertGreater(CashFlowRecord.objects.count(), 100)
        self.assertEqual(BudgetItem.objects.count(), 12 * 11)
        self.assertEqual(FinancialStatement.objects.count(), 12 + 4 + 1)
        self.assertEqual(CreditModel.objects.count(), 3)
        self.assertIsNotNone(CreditModel.objects.first().dscr)

    def test_clear_removes_only_demo(self):
        call_command('seed_finance_demo', verbosity=0)
        call_command('seed_finance_demo', '--clear', verbosity=0)
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(TenantPaymentRegistry.objects.exists())
        self.assertFalse(CashFlowRecord.objects.exists())
        self.assertFalse(FinancialStatement.objects.exists())

    def test_finance_menu_visible_and_pages_render(self):
        call_command('seed_finance_demo', verbosity=0)
        self.assertIn('finances', {item.id for item in MenuItem.generate_menu(self.admin)})

        self.client.force_login(self.admin)
        for name in PAGES:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, name)

        resp = self.client.get(reverse('finances:reg'))
        self.assertContains(resp, 'Демо: Magnum')
