from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from finances.models import PaymentCalendarEntry
from finances.services.rent_plan import generate_rent_plan, monthly_rent, plan_key
from tenants.models import Tenant


def tenant(name, **extra):
    data = dict(area=50, price=4000, phone='', email='', address='', contact='')
    data.update(extra)
    return Tenant.objects.create(name=name, **data)


@override_settings(RENT_DUE_DAY=10)
class RentPlanTest(TestCase):
    today = date(2026, 10, 13)

    def test_plan_for_lease_months(self):
        shop = tenant('Обувь', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        result = generate_rent_plan(months_ahead=4, today=self.today)

        self.assertEqual(result['created'], 3)  # окт, ноя, дек — январь вне договора
        entry = PaymentCalendarEntry.objects.get(onec_id=plan_key(shop.pk, date(2026, 11, 1)))
        self.assertEqual(entry.expected_amount, Decimal('200000.00'))
        self.assertEqual(entry.expected_date, date(2026, 11, 10))
        self.assertEqual(entry.status, PaymentCalendarEntry.Status.PLAN)

    def test_discount_until_date(self):
        shop = tenant('Книги', discount=10, discount_date=date(2026, 11, 15))
        self.assertEqual(monthly_rent(shop, date(2026, 11, 1)), Decimal('180000.00'))
        self.assertEqual(monthly_rent(shop, date(2026, 12, 1)), Decimal('200000.00'))

    def test_invoice_replaces_plan_and_archive_removes(self):
        shop = tenant('Кафе')
        generate_rent_plan(months_ahead=2, today=self.today)
        PaymentCalendarEntry.objects.create(
            tenant=shop, contract_number='Счёт 1', expected_date=date(2026, 10, 5),
            expected_amount=150000, onec_id='inv:abc',
        )
        generate_rent_plan(months_ahead=2, today=self.today)
        self.assertFalse(PaymentCalendarEntry.objects.filter(onec_id=plan_key(shop.pk, date(2026, 10, 1))).exists())
        self.assertTrue(PaymentCalendarEntry.objects.filter(onec_id=plan_key(shop.pk, date(2026, 11, 1))).exists())

        shop.is_active = False
        shop.save()
        generate_rent_plan(months_ahead=2, today=self.today)
        self.assertFalse(PaymentCalendarEntry.objects.filter(onec_id__startswith='plan:').exists())

    def test_past_due_plan_is_overdue(self):
        shop = tenant('Цветы')
        generate_rent_plan(months_ahead=1, today=date(2026, 10, 20))
        entry = PaymentCalendarEntry.objects.get(onec_id=plan_key(shop.pk, date(2026, 10, 1)))
        self.assertEqual(entry.status, PaymentCalendarEntry.Status.OVERDUE)


class BudgetForecastTest(TestCase):
    def test_run_rate_forecast(self):
        from finances.models import BudgetCategory, BudgetItem

        cat = BudgetCategory.objects.create(name='Охрана', category_type='expense')
        item = BudgetItem(category=cat, period_type='monthly', year=2026, month=10, plan=Decimal('310000'), fact=Decimal('100000'))
        # 10 из 31 дня → темп 10 000 в день → 310 000 к концу месяца
        self.assertEqual(item.effective_forecast(today=date(2026, 10, 10)), Decimal('310000.00'))
        self.assertEqual(item.effective_forecast(today=date(2026, 9, 1)), Decimal('310000'))
        self.assertEqual(item.effective_forecast(today=date(2026, 11, 2)), Decimal('100000'))
        item.forecast = Decimal('250000')
        self.assertEqual(item.effective_forecast(today=date(2026, 10, 10)), Decimal('250000'))


class CashflowForecastScenarioTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        from finances.models import CashFlowRecord

        today = timezone.localdate()
        CashFlowRecord.objects.create(
            direction=CashFlowRecord.Direction.OUTFLOW, flow_type=CashFlowRecord.FlowType.OPERATING,
            amount=Decimal('900000'), transaction_date=today - date.resolution * 10,
        )

    def test_balance_and_gap(self):
        from finances.services.forecast import forecast_cashflow

        result = forecast_cashflow(horizon_days=30, start_balance=50000)
        self.assertEqual(len(result['balance']), 30)
        self.assertEqual(result['balance'][0], 40000.0)   # 50 000 − 10 000 в день
        self.assertEqual(result['gap_dates'][0], result['labels'][5])

    def test_weekly_and_stress(self):
        from finances.services.forecast import forecast_cashflow

        weekly = forecast_cashflow(horizon_days=84, group='week', start_balance=0)
        self.assertIn(len(weekly['labels']), (12, 13))
        base = forecast_cashflow(horizon_days=7, start_balance=0)
        stress = forecast_cashflow(horizon_days=7, start_balance=0, scenario='stress')
        self.assertLess(stress['balance'][-1], base['balance'][-1])

    def test_scenarios_only_for_cfo(self):
        from django.core.cache import cache
        from django.urls import reverse
        from account.models import UserAccount

        cache.clear()
        url = reverse('finances:cashflow_forecast') + '?days=7&scenario=stress'
        for role, expected in (('owner', 'base'), ('cfo', 'stress')):
            user = UserAccount.objects.create_user(username=f'fc_{role}', password='x', role=role)
            self.client.force_login(user)
            data = self.client.get(url).json()
            self.assertEqual(data['scenario'], expected, role)
