from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from datetime import date
from decimal import Decimal

from .models import TenantPaymentRegistry, PaymentCalendarEntry, GeneratedInvoice, GeneratedInvoiceItem, BudgetCategory, BudgetItem, FinancialStatement, CashFlowRecord
from tenants.models import Tenant, TenantCategory, Room

from django.urls import reverse
from account.role_permissions import RoleEnums
from account.models import UserAccount as User


def make_tenant(name='ТестАрендатор'):
    cat  = TenantCategory.objects.create(title='Категория')
    room = Room.objects.create(number='101', map_id='r101', floor=1)
    return Tenant.objects.create(
        name=name,
        category=cat,
        room=room,
        area=50.0,
        price=5000.0,
        discount=0,
        phone='+77001234567',
        email='test@test.kz',
        address='Астана',
        contact='Иванов',
        start_date=date(2025, 1, 1),
        end_date=date(2027, 1, 1),
        discount_date=date(2025, 6, 1),
        percent=0,
        increase_type='percent',
    )


class TenantPaymentRegistryModelTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant()

    def test_create_basic(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-001',
            period=date(2026, 5, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('60000.00'),
            status=TenantPaymentRegistry.Status.PARTIAL,
        )
        self.assertEqual(p.tenant, self.tenant)
        self.assertEqual(p.contract_number, 'ДОГ-001')
        self.assertEqual(p.charged, Decimal('100000.00'))
        self.assertEqual(p.paid, Decimal('60000.00'))

    def test_balance_auto_calculated(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-002',
            period=date(2026, 5, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('40000.00'),
        )
        self.assertEqual(p.balance, Decimal('60000.00'))

    def test_balance_not_overridden_when_onec_id(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-003',
            period=date(2026, 5, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('40000.00'),
            balance=Decimal('99999.00'), 
            onec_id='ONEC-001',
        )
        self.assertEqual(p.balance, Decimal('99999.00'))

    def test_default_status_pending(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-004',
            period=date(2026, 5, 1),
            charged=Decimal('50000.00'),
            paid=Decimal('0.00'),
        )
        self.assertEqual(p.status, TenantPaymentRegistry.Status.PENDING)

    def test_default_overdue_days_zero(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-005',
            period=date(2026, 5, 1),
        )
        self.assertEqual(p.overdue_days, 0)

    def test_onec_id_nullable(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-006',
            period=date(2026, 5, 1),
        )
        self.assertIsNone(p.onec_id)

    def test_planned_and_actual_date_nullable(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-007',
            period=date(2026, 5, 1),
        )
        self.assertIsNone(p.planned_date)
        self.assertIsNone(p.actual_date)

    def test_str_representation(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-008',
            period=date(2026, 5, 1),
            status=TenantPaymentRegistry.Status.PAID,
        )
        s = str(p)
        self.assertIn('05.2026', s)
        self.assertIn(self.tenant.name, s)

    def test_all_statuses(self):
        statuses = [
            TenantPaymentRegistry.Status.PENDING,
            TenantPaymentRegistry.Status.PAID,
            TenantPaymentRegistry.Status.PARTIAL,
            TenantPaymentRegistry.Status.OVERDUE,
            TenantPaymentRegistry.Status.CANCELLED,
        ]
        for i, status in enumerate(statuses):
            p = TenantPaymentRegistry.objects.create(
                tenant=self.tenant,
                contract_number=f'ДОГ-ST-{i}',
                period=date(2026, i + 1, 1),
                status=status,
            )
            self.assertEqual(p.status, status)

    def test_overdue_days_stored(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-009',
            period=date(2026, 3, 1),
            overdue_days=15,
            status=TenantPaymentRegistry.Status.OVERDUE,
        )
        self.assertEqual(p.overdue_days, 15)

    def test_onec_id_unique(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-010',
            period=date(2026, 1, 1),
            onec_id='UNIQUE-ONEC-001',
        )
        with self.assertRaises(IntegrityError):
            TenantPaymentRegistry.objects.create(
                tenant=self.tenant,
                contract_number='ДОГ-011',
                period=date(2026, 2, 1),
                onec_id='UNIQUE-ONEC-001',
            )

    def test_unique_together_tenant_contract_period(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-012',
            period=date(2026, 4, 1),
        )
        with self.assertRaises(IntegrityError):
            TenantPaymentRegistry.objects.create(
                tenant=self.tenant,
                contract_number='ДОГ-012',
                period=date(2026, 4, 1),
            )

    def test_same_contract_different_periods_allowed(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-013',
            period=date(2026, 1, 1),
        )
        p2 = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-013',
            period=date(2026, 2, 1),
        )
        self.assertIsNotNone(p2.pk)

    def test_cascade_protect_on_tenant_delete(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-014',
            period=date(2026, 5, 1),
        )
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.tenant.delete()

    def test_ordering_by_period_desc(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant, contract_number='ДОГ-015', period=date(2026, 1, 1),
        )
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant, contract_number='ДОГ-016', period=date(2026, 3, 1),
        )
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant, contract_number='ДОГ-017', period=date(2026, 2, 1),
        )
        periods = list(TenantPaymentRegistry.objects.values_list('period', flat=True))
        self.assertEqual(periods, sorted(periods, reverse=True))

    def test_synced_at_nullable(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-018',
            period=date(2026, 5, 1),
        )
        self.assertIsNone(p.synced_at)

    def test_created_at_auto_set(self):
        p = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-019',
            period=date(2026, 5, 1),
        )
        self.assertIsNotNone(p.created_at)

    def test_related_name_from_tenant(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-020',
            period=date(2026, 5, 1),
        )
        self.assertEqual(self.tenant.payment_registry.count(), 1)


class TenantPaymentOnecSyncTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant('СинкАрендатор')

    def test_upsert_create_new(self):
        obj, created = TenantPaymentRegistry.objects.update_or_create(
            onec_id='ONEC-100',
            defaults={
                'tenant': self.tenant,
                'contract_number': 'ДОГ-100',
                'period': date(2026, 5, 1),
                'charged': Decimal('200000.00'),
                'paid': Decimal('200000.00'),
                'balance': Decimal('0.00'),
                'status': TenantPaymentRegistry.Status.PAID,
                'onec_id': 'ONEC-100',
            }
        )
        self.assertTrue(created)
        self.assertEqual(obj.status, TenantPaymentRegistry.Status.PAID)

    def test_upsert_update_existing(self):
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-101',
            period=date(2026, 5, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('0.00'),
            onec_id='ONEC-101',
            status=TenantPaymentRegistry.Status.PENDING,
        )
        obj, created = TenantPaymentRegistry.objects.update_or_create(
            onec_id='ONEC-101',
            defaults={
                'paid': Decimal('100000.00'),
                'balance': Decimal('0.00'),
                'status': TenantPaymentRegistry.Status.PAID,
            }
        )
        self.assertFalse(created)
        self.assertEqual(obj.status, TenantPaymentRegistry.Status.PAID)
        self.assertEqual(obj.paid, Decimal('100000.00'))

    def test_no_duplicates_on_multiple_syncs(self):
        for _ in range(3):
            TenantPaymentRegistry.objects.update_or_create(
                onec_id='ONEC-102',
                defaults={
                    'tenant': self.tenant,
                    'contract_number': 'ДОГ-102',
                    'period': date(2026, 6, 1),
                    'charged': Decimal('50000.00'),
                    'paid': Decimal('50000.00'),
                    'balance': Decimal('0.00'),
                    'status': TenantPaymentRegistry.Status.PAID,
                    'onec_id': 'ONEC-102',
                }
            )
        self.assertEqual(
            TenantPaymentRegistry.objects.filter(onec_id='ONEC-102').count(), 1
        )

class PaymentCalendarEntryModelTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant('КалендарьАрендатор')

    def test_create_basic(self):
        e = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-001',
            expected_date=date(2026, 6, 1),
            expected_amount=Decimal('150000.00'),
        )
        self.assertEqual(e.tenant, self.tenant)
        self.assertEqual(e.expected_amount, Decimal('150000.00'))

    def test_default_status_plan(self):
        e = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-002',
            expected_date=date(2026, 6, 1),
        )
        self.assertEqual(e.status, PaymentCalendarEntry.Status.PLAN)

    def test_all_statuses(self):
        for i, status in enumerate(PaymentCalendarEntry.Status):
            e = PaymentCalendarEntry.objects.create(
                tenant=self.tenant,
                contract_number=f'ДОГ-К-ST-{i}',
                expected_date=date(2026, i + 1, 1),
                status=status,
            )
            self.assertEqual(e.status, status)

    def test_actual_date_nullable(self):
        e = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-003',
            expected_date=date(2026, 6, 1),
        )
        self.assertIsNone(e.actual_date)

    def test_onec_id_unique(self):
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-004',
            expected_date=date(2026, 6, 1),
            onec_id='CAL-ONEC-001',
        )
        with self.assertRaises(IntegrityError):
            PaymentCalendarEntry.objects.create(
                tenant=self.tenant,
                contract_number='ДОГ-К-005',
                expected_date=date(2026, 7, 1),
                onec_id='CAL-ONEC-001',
            )

    def test_unique_together_tenant_contract_date(self):
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-006',
            expected_date=date(2026, 6, 1),
        )
        with self.assertRaises(IntegrityError):
            PaymentCalendarEntry.objects.create(
                tenant=self.tenant,
                contract_number='ДОГ-К-006',
                expected_date=date(2026, 6, 1),
            )

    def test_same_contract_different_dates_allowed(self):
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-007',
            expected_date=date(2026, 6, 1),
        )
        e2 = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-007',
            expected_date=date(2026, 7, 1),
        )
        self.assertIsNotNone(e2.pk)

    def test_protect_on_tenant_delete(self):
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-008',
            expected_date=date(2026, 6, 1),
        )
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.tenant.delete()

    def test_str_representation(self):
        e = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-009',
            expected_date=date(2026, 6, 1),
            expected_amount=Decimal('100000.00'),
            status=PaymentCalendarEntry.Status.PLAN,
        )
        s = str(e)
        self.assertIn('01.06.2026', s)
        self.assertIn(self.tenant.name, s)

    def test_related_name_from_tenant(self):
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-К-010',
            expected_date=date(2026, 6, 1),
        )
        self.assertEqual(self.tenant.payment_calendar.count(), 1)

    def test_ordering_by_expected_date(self):
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant, contract_number='ДОГ-К-011', expected_date=date(2026, 8, 1),
        )
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant, contract_number='ДОГ-К-012', expected_date=date(2026, 6, 1),
        )
        PaymentCalendarEntry.objects.create(
            tenant=self.tenant, contract_number='ДОГ-К-013', expected_date=date(2026, 7, 1),
        )
        dates = list(PaymentCalendarEntry.objects.values_list('expected_date', flat=True))
        self.assertEqual(dates, sorted(dates))

    def test_upsert_by_onec_id(self):
        obj, created = PaymentCalendarEntry.objects.update_or_create(
            onec_id='CAL-ONEC-002',
            defaults={
                'tenant': self.tenant,
                'contract_number': 'ДОГ-К-014',
                'expected_date': date(2026, 6, 1),
                'expected_amount': Decimal('100000.00'),
                'actual_amount': Decimal('100000.00'),
                'actual_date': date(2026, 6, 5),
                'status': PaymentCalendarEntry.Status.FACT,
                'onec_id': 'CAL-ONEC-002',
            }
        )
        self.assertTrue(created)
        self.assertEqual(obj.status, PaymentCalendarEntry.Status.FACT)

        obj2, created2 = PaymentCalendarEntry.objects.update_or_create(
            onec_id='CAL-ONEC-002',
            defaults={
                'actual_amount': Decimal('90000.00'),
                'status': PaymentCalendarEntry.Status.OVERDUE,
            }
        )
        self.assertFalse(created2)
        self.assertEqual(obj2.actual_amount, Decimal('90000.00'))
        self.assertEqual(obj2.status, PaymentCalendarEntry.Status.OVERDUE)
        self.assertEqual(PaymentCalendarEntry.objects.filter(onec_id='CAL-ONEC-002').count(), 1)


class GeneratedInvoiceModelTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant('СчётАрендатор')

    def test_create_basic(self):
        inv = GeneratedInvoice.objects.create(
            tenant=self.tenant,
            number='СЧ-001',
            total_amount=Decimal('150000.00'),
            vat_amount=Decimal('18000.00'),
        )
        self.assertEqual(inv.number, 'СЧ-001')
        self.assertEqual(inv.status, GeneratedInvoice.Status.CREATED)

    def test_default_status_created(self):
        inv = GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-002',
        )
        self.assertEqual(inv.status, GeneratedInvoice.Status.CREATED)

    def test_all_statuses(self):
        for i, status in enumerate(GeneratedInvoice.Status):
            inv = GeneratedInvoice.objects.create(
                tenant=self.tenant,
                number=f'СЧ-ST-{i}',
                status=status,
            )
            self.assertEqual(inv.status, status)

    def test_sent_via_nullable(self):
        inv = GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-003',
        )
        self.assertIsNone(inv.sent_via)

    def test_sent_at_nullable(self):
        inv = GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-004',
        )
        self.assertIsNone(inv.sent_at)

    def test_onec_id_unique(self):
        GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-005', onec_id='INV-ONEC-001',
        )
        with self.assertRaises(IntegrityError):
            GeneratedInvoice.objects.create(
                tenant=self.tenant, number='СЧ-006', onec_id='INV-ONEC-001',
            )

    def test_str_contains_number(self):
        inv = GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-007',
        )
        self.assertIn('СЧ-007', str(inv))

    def test_without_tenant_with_counterparty(self):
        from onec.models import Counterparty
        cp = Counterparty.objects.create(
            id_1c='TEST-CP-001',
            full_name='ТОО Тест',
            short_name='Тест',
        )
        inv = GeneratedInvoice.objects.create(
            counterparty=cp,
            number='СЧ-008',
        )
        self.assertIsNone(inv.tenant)
        self.assertEqual(inv.counterparty, cp)

    def test_protect_on_tenant_delete(self):
        GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-009',
        )
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.tenant.delete()

    def test_upsert_by_onec_id(self):
        obj, created = GeneratedInvoice.objects.update_or_create(
            onec_id='INV-ONEC-002',
            defaults={
                'tenant': self.tenant,
                'number': 'СЧ-010',
                'total_amount': Decimal('100000.00'),
                'status': GeneratedInvoice.Status.SENT,
                'onec_invoice_number': '1С-СЧ-001',
                'onec_status': 'sent',
                'onec_id': 'INV-ONEC-002',
            }
        )
        self.assertTrue(created)
        obj2, created2 = GeneratedInvoice.objects.update_or_create(
            onec_id='INV-ONEC-002',
            defaults={
                'status': GeneratedInvoice.Status.PAID,
                'onec_status': 'paid',
            }
        )
        self.assertFalse(created2)
        self.assertEqual(obj2.status, GeneratedInvoice.Status.PAID)
        self.assertEqual(GeneratedInvoice.objects.filter(onec_id='INV-ONEC-002').count(), 1)


class GeneratedInvoiceItemTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant('ПозицияАрендатор')
        self.invoice = GeneratedInvoice.objects.create(
            tenant=self.tenant,
            number='СЧ-ITEM-001',
        )

    def test_create_item(self):
        item = GeneratedInvoiceItem.objects.create(
            invoice=self.invoice,
            name='Аренда помещения',
            quantity=Decimal('1'),
            price=Decimal('150000.00'),
        )
        self.assertEqual(item.invoice, self.invoice)
        self.assertEqual(item.name, 'Аренда помещения')

    def test_total_calculated_on_save(self):
        item = GeneratedInvoiceItem.objects.create(
            invoice=self.invoice,
            name='Услуга',
            quantity=Decimal('3'),
            price=Decimal('10000.00'),
        )
        self.assertEqual(item.total, Decimal('30000.00'))

    def test_vat_calculated_on_save(self):
        item = GeneratedInvoiceItem.objects.create(
            invoice=self.invoice,
            name='Услуга НДС',
            quantity=Decimal('1'),
            price=Decimal('100000.00'),
            vat_rate=Decimal('12'),
        )
        self.assertEqual(item.vat_amount, Decimal('12000.00'))

    def test_cascade_delete_with_invoice(self):
        item = GeneratedInvoiceItem.objects.create(
            invoice=self.invoice,
            name='Каскад',
            quantity=Decimal('1'),
            price=Decimal('1000.00'),
        )
        item_id = item.id
        self.invoice.delete()
        self.assertFalse(GeneratedInvoiceItem.objects.filter(id=item_id).exists())

    def test_related_name_items(self):
        for i in range(3):
            GeneratedInvoiceItem.objects.create(
                invoice=self.invoice,
                name=f'Позиция {i}',
                quantity=Decimal('1'),
                price=Decimal('1000.00'),
            )
        self.assertEqual(self.invoice.items.count(), 3)

    def test_str_contains_name(self):
        item = GeneratedInvoiceItem.objects.create(
            invoice=self.invoice,
            name='Охрана',
            quantity=Decimal('1'),
            price=Decimal('50000.00'),
        )
        self.assertIn('Охрана', str(item))


class PaymentRegViewTest(TestCase):

    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username='fin_user', password='pass',
            role=RoleEnums.ADMINISTRATOR.value
        )
        self.tenant = make_tenant('Вью Арендатор')

        self.p_paid = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-В-001',
            period=date(2026, 3, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('100000.00'),
            balance=Decimal('0.00'),
            status=TenantPaymentRegistry.Status.PAID,
            onec_id='VIEW-001',
        )
        self.p_overdue = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-В-002',
            period=date(2026, 4, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('0.00'),
            balance=Decimal('100000.00'),
            overdue_days=20,
            status=TenantPaymentRegistry.Status.OVERDUE,
            onec_id='VIEW-002',
        )
        self.p_pending = TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-В-003',
            period=date(2026, 5, 1),
            charged=Decimal('100000.00'),
            paid=Decimal('0.00'),
            balance=Decimal('100000.00'),
            status=TenantPaymentRegistry.Status.PENDING,
            onec_id='VIEW-003',
        )
        self.url = reverse('finances:reg')


    def test_requires_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)

    def test_logged_in_returns_200(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)


    def test_context_has_entries(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        self.assertIn('entries', r.context)

    def test_context_has_all_records(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_paid, objs)
        self.assertIn(self.p_overdue, objs)
        self.assertIn(self.p_pending, objs)

    def test_context_has_tenants(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        self.assertIn('tenants', r.context)

    def test_context_has_statuses(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        self.assertIn('statuses', r.context)


    def test_color_paid_is_success(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        colors = {row['obj'].pk: row['color'] for row in r.context['entries']}
        self.assertEqual(colors[self.p_paid.pk], 'success')

    def test_color_overdue_is_danger(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        colors = {row['obj'].pk: row['color'] for row in r.context['entries']}
        self.assertEqual(colors[self.p_overdue.pk], 'danger')

    def test_color_pending_is_info(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url)
        colors = {row['obj'].pk: row['color'] for row in r.context['entries']}
        self.assertEqual(colors[self.p_pending.pk], 'info')


    def test_filter_status_paid(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'status': 'paid'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_paid, objs)
        self.assertNotIn(self.p_overdue, objs)
        self.assertNotIn(self.p_pending, objs)

    def test_filter_status_overdue(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'status': 'overdue'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_overdue, objs)
        self.assertNotIn(self.p_paid, objs)

    def test_filter_status_pending(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'status': 'pending'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_pending, objs)
        self.assertNotIn(self.p_paid, objs)


    def test_filter_search_by_tenant_name(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'search': 'Вью'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_paid, objs)

    def test_filter_search_by_contract(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'search': 'ДОГ-В-001'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_paid, objs)
        self.assertNotIn(self.p_overdue, objs)

    def test_filter_search_no_results(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'search': 'несуществующий'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertEqual(len(objs), 0)


    def test_filter_by_tenant(self):
        other_tenant = make_tenant('Другой арендатор')
        other = TenantPaymentRegistry.objects.create(
            tenant=other_tenant,
            contract_number='ДОГ-ДР-001',
            period=date(2026, 5, 1),
            onec_id='VIEW-OTHER-001',
        )
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'tenant': self.tenant.pk})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_paid, objs)
        self.assertNotIn(other, objs)


    def test_filter_period_from(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'period_from': '2026-04-01'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_overdue, objs)
        self.assertIn(self.p_pending, objs)
        self.assertNotIn(self.p_paid, objs)

    def test_filter_period_to(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'period_to': '2026-03-31'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_paid, objs)
        self.assertNotIn(self.p_overdue, objs)

    def test_filter_period_range(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {
            'period_from': '2026-04-01',
            'period_to': '2026-04-30',
        })
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.p_overdue, objs)
        self.assertNotIn(self.p_paid, objs)
        self.assertNotIn(self.p_pending, objs)

    def test_filter_values_preserved_in_context(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.get(self.url, {'status': 'paid', 'search': 'Вью'})
        self.assertEqual(r.context['f_status'], 'paid')
        self.assertEqual(r.context['f_search'], 'Вью')


    def test_no_post_create(self):
        self.client.login(username='fin_user', password='pass')
        r = self.client.post(self.url, {})
        self.assertEqual(TenantPaymentRegistry.objects.count(), 3)


class PaymentCalendarViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='fin_cal', password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.tenant = make_tenant('Календарь Арендатор')

        self.e_plan = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-КАЛ-001',
            expected_date=date(2026, 5, 10),
            expected_amount=Decimal('100000.00'),
            status=PaymentCalendarEntry.Status.PLAN,
            onec_id='CAL-V-001',
        )
        self.e_fact = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-КАЛ-002',
            expected_date=date(2026, 5, 15),
            expected_amount=Decimal('80000.00'),
            actual_amount=Decimal('80000.00'),
            actual_date=date(2026, 5, 14),
            status=PaymentCalendarEntry.Status.FACT,
            onec_id='CAL-V-002',
        )
        self.e_overdue = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-КАЛ-003',
            expected_date=date(2026, 5, 5),
            expected_amount=Decimal('50000.00'),
            status=PaymentCalendarEntry.Status.OVERDUE,
            onec_id='CAL-V-003',
        )
        self.url = reverse('finances:payment_calendar')


    def test_requires_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)

    def test_logged_in_returns_200(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)


    def test_context_has_calendar_days(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        self.assertIn('calendar_days', r.context)

    def test_calendar_has_31_days_in_may(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        self.assertEqual(len(r.context['calendar_days']), 31)

    def test_day_has_entries(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        days = {d['date'].day: d for d in r.context['calendar_days']}
        self.assertEqual(days[10]['count'], 1)
        self.assertIn(self.e_plan, days[10]['entries'])

    def test_day_planned_sum(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        days = {d['date'].day: d for d in r.context['calendar_days']}
        self.assertEqual(days[10]['planned'], Decimal('100000.00'))

    def test_day_overdue_flag(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        days = {d['date'].day: d for d in r.context['calendar_days']}
        self.assertTrue(days[5]['has_overdue'])
        self.assertFalse(days[10]['has_overdue'])

    def test_empty_day_has_zero_count(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        days = {d['date'].day: d for d in r.context['calendar_days']}
        self.assertEqual(days[1]['count'], 0)

    def test_navigation_context(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5})
        self.assertEqual(r.context['prev_month'], 4)
        self.assertEqual(r.context['next_month'], 6)

    def test_navigation_year_boundary(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 1})
        self.assertEqual(r.context['prev_month'], 12)
        self.assertEqual(r.context['prev_year'], 2025)

    def test_filter_by_status(self):
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {'year': 2026, 'month': 5, 'status': 'plan'})
        days = {d['date'].day: d for d in r.context['calendar_days']}
        self.assertIn(self.e_plan, days[10]['entries'])
        self.assertEqual(days[15]['count'], 0)

    def test_filter_by_tenant(self):
        other = make_tenant('Другой')
        PaymentCalendarEntry.objects.create(
            tenant=other,
            contract_number='ДОГ-ДР-001',
            expected_date=date(2026, 5, 10),
            expected_amount=Decimal('999.00'),
            onec_id='CAL-OTHER-001',
        )
        self.client.login(username='fin_cal', password='pass')
        r = self.client.get(self.url, {
            'year': 2026, 'month': 5, 'tenant': self.tenant.pk
        })
        days = {d['date'].day: d for d in r.context['calendar_days']}
        self.assertEqual(days[10]['count'], 1)


class PaymentCalendarDayViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='fin_day', password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.tenant = make_tenant('День Арендатор')

        self.e1 = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-Д-001',
            expected_date=date(2026, 5, 20),
            expected_amount=Decimal('120000.00'),
            actual_amount=Decimal('120000.00'),
            status=PaymentCalendarEntry.Status.FACT,
            onec_id='DAY-V-001',
        )
        self.e2 = PaymentCalendarEntry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-Д-002',
            expected_date=date(2026, 5, 20),
            expected_amount=Decimal('80000.00'),
            actual_amount=Decimal('0.00'),
            status=PaymentCalendarEntry.Status.OVERDUE,
            onec_id='DAY-V-002',
        )
        self.url = reverse('finances:payment_calendar_day',
                           args=[2026, 5, 20])

    def test_requires_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)

    def test_returns_200(self):
        self.client.login(username='fin_day', password='pass')
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)

    def test_context_has_rows(self):
        self.client.login(username='fin_day', password='pass')
        r = self.client.get(self.url)
        self.assertIn('rows', r.context)
        objs = [row['obj'] for row in r.context['rows']]
        self.assertIn(self.e1, objs)
        self.assertIn(self.e2, objs)

    def test_totals(self):
        self.client.login(username='fin_day', password='pass')
        r = self.client.get(self.url)
        self.assertEqual(r.context['total_planned'], Decimal('200000.00'))
        self.assertEqual(r.context['total_actual'],  Decimal('120000.00'))
        self.assertEqual(r.context['diff'],          Decimal('-80000.00'))

    def test_color_fact_is_success(self):
        self.client.login(username='fin_day', password='pass')
        r = self.client.get(self.url)
        colors = {row['obj'].pk: row['color'] for row in r.context['rows']}
        self.assertEqual(colors[self.e1.pk], 'success')

    def test_color_overdue_is_danger(self):
        self.client.login(username='fin_day', password='pass')
        r = self.client.get(self.url)
        colors = {row['obj'].pk: row['color'] for row in r.context['rows']}
        self.assertEqual(colors[self.e2.pk], 'danger')

    def test_valid_date_returns_200(self):
        self.client.login(username='fin_day', password='pass')
        url = reverse('finances:payment_calendar_day', args=[2026, 5, 20])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_empty_day_returns_200(self):
        self.client.login(username='fin_day', password='pass')
        url = reverse('finances:payment_calendar_day', args=[2026, 5, 1])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['rows']), 0)


class InvoiceViewsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='inv_user', password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.tenant = make_tenant('Счёт Вью Арендатор')
        self.invoice = GeneratedInvoice.objects.create(
            tenant=self.tenant,
            number='СЧ-В-001',
            total_amount=Decimal('100000.00'),
            status=GeneratedInvoice.Status.CREATED,
        )

    def test_list_requires_login(self):
        r = self.client.get(reverse('finances:invoice_list'))
        self.assertEqual(r.status_code, 302)

    def test_list_returns_200(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_list'))
        self.assertEqual(r.status_code, 200)

    def test_list_context_has_entries(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_list'))
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.invoice, objs)

    def test_list_filter_by_status(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_list'), {'status': 'paid'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertNotIn(self.invoice, objs)

    def test_list_filter_by_search(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_list'), {'search': 'СЧ-В-001'})
        objs = [row['obj'] for row in r.context['entries']]
        self.assertIn(self.invoice, objs)

    def test_color_created_is_secondary(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_list'))
        colors = {row['obj'].pk: row['color'] for row in r.context['entries']}
        self.assertEqual(colors[self.invoice.pk], 'secondary')

    def test_detail_returns_200(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_detail', args=[self.invoice.pk]))
        self.assertEqual(r.status_code, 200)

    def test_delete_invoice(self):
        self.client.login(username='inv_user', password='pass')
        inv = GeneratedInvoice.objects.create(
            tenant=self.tenant, number='СЧ-DEL-001',
            status=GeneratedInvoice.Status.CREATED,
        )
        r = self.client.post(reverse('finances:invoice_delete', args=[inv.pk]))
        self.assertRedirects(r, reverse('finances:invoice_list'))
        self.assertFalse(GeneratedInvoice.objects.filter(pk=inv.pk).exists())

    def test_cannot_delete_paid(self):
        self.client.login(username='inv_user', password='pass')
        self.invoice.status = GeneratedInvoice.Status.PAID
        self.invoice.save()
        r = self.client.post(reverse('finances:invoice_delete', args=[self.invoice.pk]))
        self.assertRedirects(r, reverse('finances:invoice_list'))
        self.assertTrue(GeneratedInvoice.objects.filter(pk=self.invoice.pk).exists())


    def test_send_invoice(self):
        self.client.login(username='inv_user', password='pass')
        r = self.client.post(
            reverse('finances:invoice_send', args=[self.invoice.pk]),
            {'sent_via': 'email'},
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'sent')
        self.assertEqual(self.invoice.sent_via, 'email')
        self.assertIsNotNone(self.invoice.sent_at)

    def test_cannot_send_already_sent(self):
        self.invoice.status = GeneratedInvoice.Status.SENT
        self.invoice.save()
        self.client.login(username='inv_user', password='pass')
        self.client.post(
            reverse('finances:invoice_send', args=[self.invoice.pk]),
            {'sent_via': 'email'},
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, GeneratedInvoice.Status.SENT)

    def test_mark_viewed(self):
        self.invoice.status = GeneratedInvoice.Status.SENT
        self.invoice.save()
        self.client.login(username='inv_user', password='pass')
        self.client.post(reverse('finances:invoice_mark_viewed', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'viewed')

    def test_cannot_mark_viewed_if_not_sent(self):
        self.client.login(username='inv_user', password='pass')
        self.client.post(reverse('finances:invoice_mark_viewed', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'created')

    def test_mark_paid_from_sent(self):
        self.invoice.status = GeneratedInvoice.Status.SENT
        self.invoice.save()
        self.client.login(username='inv_user', password='pass')
        self.client.post(reverse('finances:invoice_mark_paid', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'paid')

    def test_mark_paid_from_viewed(self):
        self.invoice.status = GeneratedInvoice.Status.VIEWED
        self.invoice.save()
        self.client.login(username='inv_user', password='pass')
        self.client.post(reverse('finances:invoice_mark_paid', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'paid')

    def test_cancel_invoice(self):
        self.client.login(username='inv_user', password='pass')
        self.client.post(reverse('finances:invoice_cancel', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'cancelled')

    def test_cannot_cancel_paid(self):
        self.invoice.status = GeneratedInvoice.Status.PAID
        self.invoice.save()
        self.client.login(username='inv_user', password='pass')
        self.client.post(reverse('finances:invoice_cancel', args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'paid')

    def test_cannot_edit_paid(self):
        self.invoice.status = GeneratedInvoice.Status.PAID
        self.invoice.save()
        self.client.login(username='inv_user', password='pass')
        r = self.client.get(reverse('finances:invoice_edit', args=[self.invoice.pk]))
        self.assertRedirects(r, reverse('finances:invoice_list'))


class BudgetCategoryModelTest(TestCase):

    def test_create_root_income(self):
        cat = BudgetCategory.objects.create(
            name='Выручка от аренды',
            category_type=BudgetCategory.Type.INCOME,
        )
        self.assertEqual(cat.category_type, 'income')
        self.assertTrue(cat.is_root)
        self.assertEqual(cat.level, 0)

    def test_create_root_expense(self):
        cat = BudgetCategory.objects.create(
            name='Операционные расходы',
            category_type=BudgetCategory.Type.EXPENSE,
        )
        self.assertEqual(cat.category_type, 'expense')

    def test_create_child_category(self):
        parent = BudgetCategory.objects.create(
            name='Доходы', category_type=BudgetCategory.Type.INCOME,
        )
        child = BudgetCategory.objects.create(
            name='Аренда офисов',
            category_type=BudgetCategory.Type.INCOME,
            parent=parent,
        )
        self.assertEqual(child.parent, parent)
        self.assertFalse(child.is_root)
        self.assertEqual(child.level, 1)

    def test_grandchild_level(self):
        root = BudgetCategory.objects.create(
            name='Доходы', category_type=BudgetCategory.Type.INCOME,
        )
        child = BudgetCategory.objects.create(
            name='Аренда', category_type=BudgetCategory.Type.INCOME, parent=root,
        )
        grandchild = BudgetCategory.objects.create(
            name='Офисы', category_type=BudgetCategory.Type.INCOME, parent=child,
        )
        self.assertEqual(grandchild.level, 2)

    def test_children_related_name(self):
        parent = BudgetCategory.objects.create(
            name='Расходы', category_type=BudgetCategory.Type.EXPENSE,
        )
        for i in range(3):
            BudgetCategory.objects.create(
                name=f'Подкатегория {i}',
                category_type=BudgetCategory.Type.EXPENSE,
                parent=parent,
            )
        self.assertEqual(parent.children.count(), 3)

    def test_cascade_delete_children(self):
        parent = BudgetCategory.objects.create(
            name='Родитель', category_type=BudgetCategory.Type.INCOME,
        )
        child = BudgetCategory.objects.create(
            name='Дочерняя', category_type=BudgetCategory.Type.INCOME, parent=parent,
        )
        child_id = child.id
        parent.delete()
        self.assertFalse(BudgetCategory.objects.filter(id=child_id).exists())

    def test_code_unique(self):
        BudgetCategory.objects.create(
            name='Кат 1', category_type=BudgetCategory.Type.INCOME, code='CAT-001',
        )
        with self.assertRaises(IntegrityError):
            BudgetCategory.objects.create(
                name='Кат 2', category_type=BudgetCategory.Type.INCOME, code='CAT-001',
            )

    def test_code_nullable(self):
        cat = BudgetCategory.objects.create(
            name='Без кода', category_type=BudgetCategory.Type.INCOME,
        )
        self.assertIsNone(cat.code)

    def test_is_active_default_true(self):
        cat = BudgetCategory.objects.create(
            name='Активная', category_type=BudgetCategory.Type.INCOME,
        )
        self.assertTrue(cat.is_active)

    def test_str_root(self):
        cat = BudgetCategory.objects.create(
            name='Выручка', category_type=BudgetCategory.Type.INCOME,
        )
        self.assertEqual(str(cat), 'Выручка')

    def test_str_child(self):
        parent = BudgetCategory.objects.create(
            name='Доходы', category_type=BudgetCategory.Type.INCOME,
        )
        child = BudgetCategory.objects.create(
            name='Аренда', category_type=BudgetCategory.Type.INCOME, parent=parent,
        )
        self.assertIn('Аренда', str(child))
        self.assertIn('Доходы', str(child))

    def test_ordering(self):
        BudgetCategory.objects.create(
            name='Б', category_type=BudgetCategory.Type.INCOME, order=2,
        )
        BudgetCategory.objects.create(
            name='А', category_type=BudgetCategory.Type.INCOME, order=1,
        )
        cats = list(BudgetCategory.objects.filter(category_type='income'))
        self.assertEqual(cats[0].name, 'А')


class BudgetItemModelTest(TestCase):

    def setUp(self):
        self.cat_income = BudgetCategory.objects.create(
            name='Выручка', category_type=BudgetCategory.Type.INCOME,
        )
        self.cat_expense = BudgetCategory.objects.create(
            name='Расходы', category_type=BudgetCategory.Type.EXPENSE,
        )

    def test_create_monthly(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=5,
            plan=Decimal('500000.00'),
            fact=Decimal('480000.00'),
            forecast=Decimal('490000.00'),
        )
        self.assertEqual(item.year, 2026)
        self.assertEqual(item.month, 5)
        self.assertEqual(item.plan, Decimal('500000.00'))

    def test_create_quarterly(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.QUARTERLY,
            year=2026, quarter=2,
            plan=Decimal('1500000.00'),
        )
        self.assertEqual(item.quarter, 2)

    def test_create_yearly(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.YEARLY,
            year=2026,
            plan=Decimal('6000000.00'),
        )
        self.assertEqual(item.period_type, 'yearly')

    def test_variance_positive(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=1,
            plan=Decimal('100000.00'),
            fact=Decimal('120000.00'),
        )
        self.assertEqual(item.variance, Decimal('20000.00'))

    def test_variance_negative(self):
        item = BudgetItem.objects.create(
            category=self.cat_expense,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=2,
            plan=Decimal('100000.00'),
            fact=Decimal('80000.00'),
        )
        self.assertEqual(item.variance, Decimal('-20000.00'))

    def test_variance_pct(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=3,
            plan=Decimal('100000.00'),
            fact=Decimal('110000.00'),
        )
        self.assertEqual(item.variance_pct, 10.0)

    def test_variance_pct_none_when_plan_zero(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=4,
            plan=Decimal('0.00'),
            fact=Decimal('50000.00'),
        )
        self.assertIsNone(item.variance_pct)

    def test_execution_pct(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=6,
            plan=Decimal('200000.00'),
            fact=Decimal('150000.00'),
        )
        self.assertEqual(item.execution_pct, 75.0)

    def test_unique_together(self):
        BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=7, quarter=None,
            plan=Decimal('100000.00'),
            )
        exists = BudgetItem.objects.filter(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=7,
            ).count()
        self.assertEqual(exists, 1)

        obj, created = BudgetItem.objects.get_or_create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=7,
            defaults={'plan': Decimal('200000.00')},
            )
        self.assertFalse(created)
        self.assertEqual(BudgetItem.objects.filter(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=7,
            ).count(), 1)

    def test_different_months_allowed(self):
        BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=8,
            plan=Decimal('100000.00'),
        )
        item2 = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=9,
            plan=Decimal('100000.00'),
        )
        self.assertIsNotNone(item2.pk)

    def test_protect_on_category_delete(self):
        BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=10,
            plan=Decimal('100000.00'),
        )
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.cat_income.delete()

    def test_period_label_monthly(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=5,
            plan=Decimal('100000.00'),
        )
        self.assertEqual(item.get_period_label(), '05.2026')

    def test_period_label_quarterly(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.QUARTERLY,
            year=2026, quarter=3,
            plan=Decimal('100000.00'),
        )
        self.assertEqual(item.get_period_label(), 'Q3 2026')

    def test_period_label_yearly(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.YEARLY,
            year=2026,
            plan=Decimal('100000.00'),
        )
        self.assertEqual(item.get_period_label(), '2026')

    def test_str(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=11,
            plan=Decimal('300000.00'),
        )
        s = str(item)
        self.assertIn('Выручка', s)
        self.assertIn('300000', s)

    def test_defaults(self):
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=12,
        )
        self.assertEqual(item.plan, Decimal('0'))
        self.assertEqual(item.fact, Decimal('0'))
        self.assertEqual(item.forecast, Decimal('0'))


class FinancialStatementModelTest(TestCase):

    def setUp(self):
        self.cat_income = BudgetCategory.objects.create(
            name='Выручка ОПиУ', category_type=BudgetCategory.Type.INCOME,
        )
        self.cat_expense = BudgetCategory.objects.create(
            name='Расходы ОПиУ', category_type=BudgetCategory.Type.EXPENSE,
        )

    def _make_statement(self, **kwargs):
        defaults = dict(
            period_type=FinancialStatement.Period.MONTHLY,
            year=2026, month=5,
            revenue_plan=Decimal('1000000'),
            revenue_fact=Decimal('900000'),
            revenue_forecast=Decimal('950000'),
            ebitda_plan=Decimal('400000'),
            ebitda_fact=Decimal('360000'),
            ebitda_forecast=Decimal('380000'),
            operating_profit_plan=Decimal('300000'),
            operating_profit_fact=Decimal('270000'),
            net_profit_plan=Decimal('200000'),
            net_profit_fact=Decimal('180000'),
            net_profit_forecast=Decimal('190000'),
        )
        defaults.update(kwargs)
        return FinancialStatement.objects.create(**defaults)

    def test_create_monthly(self):
        s = self._make_statement()
        self.assertEqual(s.year, 2026)
        self.assertEqual(s.month, 5)
        self.assertEqual(s.period_type, 'monthly')

    def test_create_quarterly(self):
        s = self._make_statement(
            period_type=FinancialStatement.Period.QUARTERLY,
            month=None, quarter=2,
        )
        self.assertEqual(s.quarter, 2)

    def test_create_yearly(self):
        s = self._make_statement(
            period_type=FinancialStatement.Period.YEARLY,
            month=None,
        )
        self.assertEqual(s.period_type, 'yearly')

    def test_str_monthly(self):
        s = self._make_statement()
        self.assertEqual(str(s), 'ОПиУ | 05.2026')

    def test_str_quarterly(self):
        s = self._make_statement(
            period_type=FinancialStatement.Period.QUARTERLY,
            month=None, quarter=1,
        )
        self.assertEqual(str(s), 'ОПиУ | Q1 2026')

    def test_str_yearly(self):
        s = self._make_statement(
            period_type=FinancialStatement.Period.YEARLY,
            month=None,
        )
        self.assertEqual(str(s), 'ОПиУ | 2026')

    def test_ebitda_margin_fact(self):
        s = self._make_statement(
            revenue_fact=Decimal('1000000'),
            ebitda_fact=Decimal('400000'),
        )
        self.assertEqual(s.ebitda_margin_fact, 40.0)

    def test_net_margin_fact(self):
        s = self._make_statement(
            revenue_fact=Decimal('1000000'),
            net_profit_fact=Decimal('200000'),
        )
        self.assertEqual(s.net_margin_fact, 20.0)

    def test_operating_margin_fact(self):
        s = self._make_statement(
            revenue_fact=Decimal('1000000'),
            operating_profit_fact=Decimal('300000'),
        )
        self.assertEqual(s.operating_margin_fact, 30.0)

    def test_margin_none_when_revenue_zero(self):
        s = self._make_statement(revenue_fact=Decimal('0'))
        self.assertIsNone(s.ebitda_margin_fact)
        self.assertIsNone(s.net_margin_fact)
        self.assertIsNone(s.operating_margin_fact)

    def test_revenue_variance(self):
        s = self._make_statement(
            revenue_plan=Decimal('1000000'),
            revenue_fact=Decimal('900000'),
        )
        self.assertEqual(s.revenue_variance, Decimal('-100000'))

    def test_net_profit_variance(self):
        s = self._make_statement(
            net_profit_plan=Decimal('200000'),
            net_profit_fact=Decimal('220000'),
        )
        self.assertEqual(s.net_profit_variance, Decimal('20000'))

    def test_ebitda_variance(self):
        s = self._make_statement(
            ebitda_plan=Decimal('400000'),
            ebitda_fact=Decimal('380000'),
        )
        self.assertEqual(s.ebitda_variance, Decimal('-20000'))

    def test_defaults_zero(self):
        s = FinancialStatement.objects.create(
            period_type=FinancialStatement.Period.MONTHLY,
            year=2026, month=6,
        )
        self.assertEqual(s.revenue_plan, Decimal('0'))
        self.assertEqual(s.net_profit_fact, Decimal('0'))
        self.assertEqual(s.ebitda_forecast, Decimal('0'))

    def test_unique_together(self):
        self._make_statement()
        obj, created = FinancialStatement.objects.get_or_create(
            period_type=FinancialStatement.Period.MONTHLY,
            year=2026, month=5,
            defaults={'revenue_plan': Decimal('999999')},
            )
        self.assertFalse(created)
        self.assertEqual(
            FinancialStatement.objects.filter(period_type='monthly', year=2026, month=5).count(), 1
            )

    def test_different_months_allowed(self):
        self._make_statement(month=1)
        s2 = self._make_statement(month=2)
        self.assertIsNotNone(s2.pk)

    def test_revenue_categories_m2m(self):
        s = self._make_statement()
        s.revenue_categories.add(self.cat_income)
        self.assertIn(self.cat_income, s.revenue_categories.all())

    def test_expense_categories_m2m(self):
        s = self._make_statement()
        s.expense_categories.add(self.cat_expense)
        self.assertIn(self.cat_expense, s.expense_categories.all())

    def test_revenue_categories_empty_by_default(self):
        s = self._make_statement()
        self.assertEqual(s.revenue_categories.count(), 0)

    def test_period_label_monthly(self):
        s = self._make_statement(month=3)
        self.assertEqual(s.get_period_label(), '03.2026')

    def test_period_label_quarterly(self):
        s = self._make_statement(
            period_type=FinancialStatement.Period.QUARTERLY,
            month=None, quarter=4,
        )
        self.assertEqual(s.get_period_label(), 'Q4 2026')

    def test_related_name_revenue_statements(self):
        s = self._make_statement()
        s.revenue_categories.add(self.cat_income)
        self.assertIn(s, self.cat_income.revenue_statements.all())

    def test_related_name_expense_statements(self):
        s = self._make_statement()
        s.expense_categories.add(self.cat_expense)
        self.assertIn(s, self.cat_expense.expense_statements.all())


class CashFlowRecordModelTest(TestCase):

    def setUp(self):
        self.cat = BudgetCategory.objects.create(
            name='Поступления от аренды',
            category_type=BudgetCategory.Type.INCOME,
        )
        from onec.models import Counterparty
        self.counterparty = Counterparty.objects.create(
            id_1c='CF-CP-001',
            full_name='ТОО Тест Контрагент',
            short_name='ТОО Тест',
        )

    def _make_record(self, **kwargs):
        from datetime import date
        defaults = dict(
            direction=CashFlowRecord.Direction.INFLOW,
            flow_type=CashFlowRecord.FlowType.OPERATING,
            amount=Decimal('500000.00'),
            currency='KZT',
            transaction_date=date(2026, 5, 15),
        )
        defaults.update(kwargs)
        return CashFlowRecord.objects.create(**defaults)

    def test_create_inflow(self):
        r = self._make_record()
        self.assertEqual(r.direction, 'inflow')
        self.assertEqual(r.amount, Decimal('500000.00'))
        self.assertTrue(r.is_inflow)
        self.assertFalse(r.is_outflow)

    def test_create_outflow(self):
        r = self._make_record(
            direction=CashFlowRecord.Direction.OUTFLOW,
            amount=Decimal('200000.00'),
        )
        self.assertEqual(r.direction, 'outflow')
        self.assertTrue(r.is_outflow)
        self.assertFalse(r.is_inflow)

    def test_all_flow_types(self):
        from datetime import date
        for i, ft in enumerate(CashFlowRecord.FlowType):
            r = self._make_record(
                flow_type=ft,
                transaction_date=date(2026, 5, i + 1),
            )
            self.assertEqual(r.flow_type, ft)

    def test_str(self):
        r = self._make_record()
        s = str(r)
        self.assertIn('Поступление', s)
        self.assertIn('15.05.2026', s)
        self.assertIn('500000', s)

    def test_counterparty_fk(self):
        r = self._make_record(counterparty=self.counterparty)
        self.assertEqual(r.counterparty, self.counterparty)
        self.assertIn(r, self.counterparty.cash_flow_records.all())

    def test_budget_category_fk(self):
        r = self._make_record(budget_category=self.cat)
        self.assertEqual(r.budget_category, self.cat)
        self.assertIn(r, self.cat.cash_flow_records.all())

    def test_counterparty_nullable(self):
        r = self._make_record()
        self.assertIsNone(r.counterparty)

    def test_budget_category_nullable(self):
        r = self._make_record()
        self.assertIsNone(r.budget_category)

    def test_onec_id_unique(self):
        self._make_record(onec_id='CF-ONEC-001')
        with self.assertRaises(IntegrityError):
            self._make_record(onec_id='CF-ONEC-001')

    def test_onec_id_nullable(self):
        r = self._make_record()
        self.assertIsNone(r.onec_id)

    def test_set_null_on_counterparty_delete(self):
        r = self._make_record(counterparty=self.counterparty)
        self.counterparty.delete()
        r.refresh_from_db()
        self.assertIsNone(r.counterparty)

    def test_set_null_on_category_delete(self):
        r = self._make_record(budget_category=self.cat)
        self.cat.delete()
        r.refresh_from_db()
        self.assertIsNone(r.budget_category)

    def test_default_currency_kzt(self):
        r = self._make_record()
        self.assertEqual(r.currency, 'KZT')

    def test_value_date_nullable(self):
        r = self._make_record()
        self.assertIsNone(r.value_date)

    def test_description_nullable(self):
        r = self._make_record()
        self.assertIsNone(r.description)

    def test_upsert_by_onec_id(self):
        from datetime import date
        obj, created = CashFlowRecord.objects.update_or_create(
            onec_id='CF-ONEC-002',
            defaults={
                'direction': CashFlowRecord.Direction.INFLOW,
                'flow_type': CashFlowRecord.FlowType.OPERATING,
                'amount': Decimal('300000.00'),
                'currency': 'KZT',
                'transaction_date': date(2026, 5, 20),
                'onec_id': 'CF-ONEC-002',
            }
        )
        self.assertTrue(created)

        obj2, created2 = CashFlowRecord.objects.update_or_create(
            onec_id='CF-ONEC-002',
            defaults={'amount': Decimal('350000.00')}
        )
        self.assertFalse(created2)
        self.assertEqual(obj2.amount, Decimal('350000.00'))
        self.assertEqual(
            CashFlowRecord.objects.filter(onec_id='CF-ONEC-002').count(), 1
        )

    def test_ordering_by_date_desc(self):
        from datetime import date
        self._make_record(transaction_date=date(2026, 3, 1))
        self._make_record(transaction_date=date(2026, 5, 1))
        self._make_record(transaction_date=date(2026, 1, 1))
        dates = list(
            CashFlowRecord.objects.values_list('transaction_date', flat=True)
        )
        self.assertEqual(dates, sorted(dates, reverse=True))


class BudgetViewsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.cfo_user = User.objects.create_user(
            username='cfo_user', password='pass',
            role=RoleEnums.CFO.value,
        )
        self.accountant_user = User.objects.create_user(
            username='accountant_user', password='pass',
            role=RoleEnums.CHIEF_ACCOUNTANT.value,
        )
        self.staff_user = User.objects.create_user(
            username='budget_staff', password='pass',
            role=RoleEnums.STAFF.value,
        )
        self.cat_income = BudgetCategory.objects.create(
            name='Доходы тест', category_type=BudgetCategory.Type.INCOME,
        )
        self.cat_expense = BudgetCategory.objects.create(
            name='Расходы тест', category_type=BudgetCategory.Type.EXPENSE,
        )
        self.item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=5,
            plan=Decimal('500000'),
            fact=Decimal('450000'),
            forecast=Decimal('480000'),
        )
        self.overrun_item = BudgetItem.objects.create(
            category=self.cat_expense,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=5,
            plan=Decimal('100000'),
            fact=Decimal('120000'),
        )


    def test_list_requires_login(self):
        r = self.client.get(reverse('finances:budget_list'))
        self.assertEqual(r.status_code, 302)

    def test_staff_cannot_access(self):
        self.client.login(username='budget_staff', password='pass')
        r = self.client.get(reverse('finances:budget_list'))
        self.assertEqual(r.status_code, 403)

    def test_cfo_can_access_list(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'))
        self.assertEqual(r.status_code, 200)

    def test_accountant_can_access_list(self):
        self.client.login(username='accountant_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'))
        self.assertEqual(r.status_code, 200)

    def test_list_context_has_rows(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'), {'year': 2026, 'month': 5})
        self.assertIn('rows', r.context)

    def test_cfo_can_edit(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'))
        self.assertTrue(r.context['can_edit'])

    def test_accountant_cannot_edit(self):
        self.client.login(username='accountant_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'))
        self.assertFalse(r.context['can_edit'])

    def test_overrun_signal(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'), {'year': 2026, 'month': 5})
        rows = r.context['rows']
        expense_row = next(row for row in rows if row['cat'] == self.cat_expense)
        self.assertTrue(expense_row['overrun'])

    def test_no_overrun_for_income(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'), {'year': 2026, 'month': 5})
        rows = r.context['rows']
        income_row = next(row for row in rows if row['cat'] == self.cat_income)
        self.assertFalse(income_row['overrun'])

    def test_has_overrun_flag(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_list'), {'year': 2026, 'month': 5})
        self.assertTrue(r.context['has_overrun'])


    def test_detail_returns_200(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_detail', args=[self.cat_income.pk]))
        self.assertEqual(r.status_code, 200)

    def test_detail_context_has_rows(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_detail', args=[self.cat_income.pk]))
        self.assertIn('rows', r.context)
        items = [row['item'] for row in r.context['rows']]
        self.assertIn(self.item, items)

    def test_detail_variance(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_detail', args=[self.cat_income.pk]))
        row = r.context['rows'][0]
        self.assertEqual(row['variance'], Decimal('-50000'))

    def test_detail_exec_pct(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.get(reverse('finances:budget_detail', args=[self.cat_income.pk]))
        row = r.context['rows'][0]
        self.assertEqual(row['exec_pct'], 90.0)

    def test_detail_404_on_missing(self):
        self.client.login(username='cfo_user', password='pass')
        from finances.models import BudgetCategory
        self.assertFalse(BudgetCategory.objects.filter(pk=999999).exists())


    def test_create_requires_cfo(self):
        self.client.login(username='accountant_user', password='pass')
        r = self.client.get(
            reverse('finances:budget_item_create', args=[self.cat_income.pk])
        )
        self.assertEqual(r.status_code, 403)

    def test_cfo_can_create(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.post(
            reverse('finances:budget_item_create', args=[self.cat_income.pk]),
            {
                'period_type': 'monthly',
                'year': 2026, 'month': 6,
                'plan': '600000', 'fact': '0', 'forecast': '0',
            }
        )
        self.assertRedirects(r, reverse('finances:budget_detail', args=[self.cat_income.pk]))
        self.assertTrue(BudgetItem.objects.filter(category=self.cat_income, month=6).exists())


    def test_edit_requires_cfo(self):
        self.client.login(username='accountant_user', password='pass')
        r = self.client.get(reverse('finances:budget_item_edit', args=[self.item.pk]))
        self.assertEqual(r.status_code, 403)

    def test_cfo_can_edit_item(self):
        self.client.login(username='cfo_user', password='pass')
        r = self.client.post(
            reverse('finances:budget_item_edit', args=[self.item.pk]),
            {
                'period_type': 'monthly',
                'year': 2026, 'month': 5,
                'plan': '550000', 'fact': '450000', 'forecast': '480000',
            }
        )
        self.assertRedirects(r, reverse('finances:budget_detail', args=[self.cat_income.pk]))
        self.item.refresh_from_db()
        self.assertEqual(self.item.plan, Decimal('550000'))


    def test_delete_requires_cfo(self):
        self.client.login(username='accountant_user', password='pass')
        r = self.client.post(reverse('finances:budget_item_delete', args=[self.item.pk]))
        self.assertEqual(r.status_code, 403)

    def test_cfo_can_delete(self):
        self.client.login(username='cfo_user', password='pass')
        item = BudgetItem.objects.create(
            category=self.cat_income,
            period_type=BudgetItem.Period.MONTHLY,
            year=2026, month=7,
            plan=Decimal('100000'),
        )
        r = self.client.post(reverse('finances:budget_item_delete', args=[item.pk]))
        self.assertRedirects(r, reverse('finances:budget_detail', args=[self.cat_income.pk]))
        self.assertFalse(BudgetItem.objects.filter(pk=item.pk).exists())

# ─── BE-5.14: Invoice delivery ────────────────────────────────────────────────

from django.core import mail
from django.test import override_settings
from unittest.mock import patch, MagicMock

from finances.models import GeneratedInvoice, GeneratedInvoiceItem
from finances.services.notifications import (
    send_invoice_via_email,
    send_invoice_via_messenger,
    _resolve_recipient_email,
    _mark_sent,
)


def _make_invoice(tenant=None, number='INV-001', status=None):
    status = status or GeneratedInvoice.Status.CREATED
    return GeneratedInvoice.objects.create(
        number=number,
        total_amount=Decimal('150000.00'),
        vat_amount=Decimal('18000.00'),
        status=status,
        tenant=tenant,
    )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   DEFAULT_FROM_EMAIL='noreply@test.kz')
class SendInvoiceEmailTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant('email_test_tenant')

    def test_email_sent_to_tenant(self):
        invoice = _make_invoice(tenant=self.tenant)
        GeneratedInvoiceItem.objects.create(
            invoice=invoice, name='Аренда', quantity=1,
            price=Decimal('132000'), total=Decimal('132000'),
        )
        result = send_invoice_via_email(invoice)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('INV-001', mail.outbox[0].subject)
        self.assertIn('test@test.kz', mail.outbox[0].to)

    def test_email_sets_status_sent(self):
        invoice = _make_invoice(tenant=self.tenant)
        send_invoice_via_email(invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, GeneratedInvoice.Status.SENT)
        self.assertEqual(invoice.sent_via, GeneratedInvoice.SentVia.EMAIL)
        self.assertIsNotNone(invoice.sent_at)

    def test_email_returns_false_without_recipient(self):
        invoice = _make_invoice(tenant=None)
        result = send_invoice_via_email(invoice)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_content_is_html(self):
        invoice = _make_invoice(tenant=self.tenant)
        send_invoice_via_email(invoice)
        self.assertEqual(mail.outbox[0].content_subtype, 'html')
        self.assertIn('150', mail.outbox[0].body)

    def test_email_returns_false_on_smtp_error(self):
        invoice = _make_invoice(tenant=self.tenant)
        with patch('finances.services.notifications.EmailMessage.send', side_effect=Exception('SMTP down')):
            result = send_invoice_via_email(invoice)
        self.assertFalse(result)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, GeneratedInvoice.Status.CREATED)


class SendInvoiceMessengerTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant('msg_tenant')

    def test_whatsapp_marks_sent(self):
        invoice = _make_invoice(tenant=self.tenant)
        result = send_invoice_via_messenger(invoice, 'whatsapp')
        self.assertTrue(result)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, GeneratedInvoice.Status.SENT)
        self.assertEqual(invoice.sent_via, 'whatsapp')
        self.assertIsNotNone(invoice.sent_at)

    def test_telegram_marks_sent(self):
        invoice = _make_invoice(tenant=self.tenant)
        result = send_invoice_via_messenger(invoice, 'telegram')
        self.assertTrue(result)
        invoice.refresh_from_db()
        self.assertEqual(invoice.sent_via, 'telegram')


class ResolveRecipientEmailTest(TestCase):
    def test_returns_tenant_email(self):
        tenant = make_tenant('resolve_tenant')
        invoice = _make_invoice(tenant=tenant)
        email = _resolve_recipient_email(invoice)
        self.assertEqual(email, 'test@test.kz')

    def test_returns_none_when_no_tenant_no_cp(self):
        invoice = _make_invoice(tenant=None)
        email = _resolve_recipient_email(invoice)
        self.assertIsNone(email)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class InvoiceSendViewTest(TestCase):
    def setUp(self):
        from account.models import UserAccount
        self.user = UserAccount.objects.create_user(
            username='fin_user', password='pass', role='administrator', is_superuser=True
        )
        self.client.login(username='fin_user', password='pass')
        self.tenant = make_tenant('view_tenant')

    def _invoice(self):
        return _make_invoice(tenant=self.tenant, number='VIEW-001')

    def test_post_email_sends_mail(self):
        invoice = self._invoice()
        url = f'/finances/invoices/{invoice.pk}/send/'
        self.client.post(url, {'sent_via': 'email'})
        self.assertGreaterEqual(len(mail.outbox), 1)

    def test_post_manual_marks_sent(self):
        invoice = self._invoice()
        url = f'/finances/invoices/{invoice.pk}/send/'
        self.client.post(url, {'sent_via': 'manual'})
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, GeneratedInvoice.Status.SENT)
        self.assertEqual(invoice.sent_via, 'manual')

    def test_post_already_sent_ignored(self):
        invoice = _make_invoice(tenant=self.tenant, number='SENT-001', status=GeneratedInvoice.Status.SENT)
        url = f'/finances/invoices/{invoice.pk}/send/'
        self.client.post(url, {'sent_via': 'email'})
        invoice.refresh_from_db()
        self.assertIsNone(invoice.sent_at)


# ─── COLLAB-3: Finance screens smoke-test ─────────────────────────────────────

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from account.models import UserAccount
from account.role_permissions import RoleEnums


def _fin_user(username, role):
    user, _ = UserAccount.objects.get_or_create(
        username=username,
        defaults={'role': role, 'is_superuser': True},
    )
    user.role = role
    user.set_password('pass')
    user.save()
    return user


@override_settings(ALLOWED_HOSTS=['testserver'])
class FinanceSmokeTest(TestCase):
    """Smoke-test цепочки финансовых экранов и разграничение ролей."""

    FINANCE_URLS = [
        ('finances:reg', {}),
        ('finances:payment_calendar', {}),
        ('finances:invoice_list', {}),
        ('finances:budget_list', {}),
        ('finances:opiu', {}),
        ('finances:cashflow', {}),
    ]

    def setUp(self):
        self.cfo = _fin_user('collab_cfo', RoleEnums.CFO.value)
        self.owner = _fin_user('collab_owner', RoleEnums.OWNER.value)
        self.accountant = _fin_user('collab_ca', RoleEnums.CHIEF_ACCOUNTANT.value)
        self.staff = _fin_user('collab_staff', RoleEnums.STAFF.value)

    def _get_all(self, user, urls):
        self.client.login(username=user.username, password='pass')
        results = []
        for name, kwargs in urls:
            url = reverse(name, kwargs=kwargs)
            r = self.client.get(url)
            results.append((name, r.status_code))
        self.client.logout()
        return results

    def test_cfo_sees_all_finance_screens(self):
        for name, code in self._get_all(self.cfo, self.FINANCE_URLS):
            with self.subTest(screen=name):
                self.assertEqual(code, 200, f'CFO: {name} returned {code}')

    def test_cfo_sees_credit_model(self):
        self.client.login(username=self.cfo.username, password='pass')
        r = self.client.get(reverse('finances:credit_model_list'))
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get(reverse('finances:credit_model_create'))
        self.assertEqual(r2.status_code, 200)

    def test_owner_sees_credit_model(self):
        self.client.login(username=self.owner.username, password='pass')
        self.assertEqual(self.client.get(reverse('finances:credit_model_list')).status_code, 200)

    def test_chief_accountant_readonly_finance_screens(self):
        for name, code in self._get_all(self.accountant, self.FINANCE_URLS):
            with self.subTest(screen=name):
                self.assertEqual(code, 200)

    def test_chief_accountant_denied_credit_model(self):
        self.client.login(username=self.accountant.username, password='pass')
        r = self.client.get(reverse('finances:credit_model_list'))
        self.assertIn(r.status_code, (302, 403))

    def test_chief_accountant_cannot_create_budget_item(self):
        from finances.models import BudgetCategory
        cat = BudgetCategory.objects.create(name='Smoke Cat', category_type='expense')
        self.client.login(username=self.accountant.username, password='pass')
        r = self.client.get(reverse('finances:budget_item_create', kwargs={'category_pk': cat.pk}))
        self.assertEqual(r.status_code, 403)

    def test_staff_denied_finance_screens(self):
        for name, code in self._get_all(self.staff, self.FINANCE_URLS[:2]):
            with self.subTest(screen=name):
                self.assertIn(code, (302, 403))

    def test_finance_chain_urls_resolve(self):
        names = [
            'finances:reg', 'finances:payment_calendar', 'finances:invoice_list',
            'finances:budget_list', 'finances:opiu', 'finances:cashflow',
            'finances:credit_model_list',
        ]
        for name in names:
            with self.subTest(url=name):
                self.assertTrue(reverse(name))


# ─── BE-5.13: ExchangeRate + fetch_exchange_rates ─────────────────────────────

from unittest.mock import patch, MagicMock
from decimal import Decimal
from finances.models import ExchangeRate
from finances.services.nbrk import fetch_nbrk_rates, _parse_nbrk_xml, save_nbrk_rates


SAMPLE_NBRK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rates>
  <item>
    <title>USD</title>
    <description>475.46</description>
  </item>
  <item>
    <title>EUR</title>
    <description>512.30</description>
  </item>
  <item>
    <title>RUB</title>
    <description>5.20</description>
  </item>
  <item>
    <title>CNY</title>
    <description>65.80</description>
  </item>
  <item>
    <title>KZT</title>
    <description>1.00</description>
  </item>
</rates>"""


class ExchangeRateModelTest(TestCase):
    def setUp(self):
        ExchangeRate.objects.create(currency='USD', date=date(2026, 5, 20), rate=Decimal('475.46'))
        ExchangeRate.objects.create(currency='EUR', date=date(2026, 5, 20), rate=Decimal('512.30'))

    def test_str_representation(self):
        er = ExchangeRate.objects.get(currency='USD', date=date(2026, 5, 20))
        self.assertIn('USD', str(er))
        self.assertIn('475.46', str(er))

    def test_unique_together_constraint(self):
        with self.assertRaises(Exception):
            ExchangeRate.objects.create(currency='USD', date=date(2026, 5, 20), rate=Decimal('480.00'))

    def test_convert_to_kzt(self):
        result = ExchangeRate.convert(100, 'USD', 'KZT', date=date(2026, 5, 20))
        self.assertEqual(result, Decimal('47546.00'))

    def test_convert_from_kzt(self):
        result = ExchangeRate.convert(Decimal('47546'), 'KZT', 'USD', date=date(2026, 5, 20))
        self.assertAlmostEqual(float(result), 100.0, places=4)

    def test_convert_same_currency(self):
        result = ExchangeRate.convert(500, 'KZT', 'KZT', date=date(2026, 5, 20))
        self.assertEqual(result, Decimal('500'))

    def test_convert_cross_currency(self):
        result = ExchangeRate.convert(1, 'USD', 'EUR', date=date(2026, 5, 20))
        expected = Decimal('475.46') / Decimal('512.30')
        self.assertAlmostEqual(float(result), float(expected), places=4)

    def test_convert_missing_rate_raises(self):
        with self.assertRaises(ValueError):
            ExchangeRate.convert(100, 'GBP', 'KZT', date=date(2026, 5, 20))

    def test_convert_uses_latest_available_date(self):
        """convert() с датой после последней записи должен взять ближайшую раннюю."""
        result = ExchangeRate.convert(1, 'USD', 'KZT', date=date(2026, 5, 25))
        self.assertEqual(result, Decimal('475.46'))


class NbrkParseTest(TestCase):
    def test_parse_returns_tracked_currencies(self):
        result = _parse_nbrk_xml(SAMPLE_NBRK_XML, date(2026, 5, 20))
        currencies = {r['currency'] for r in result}
        self.assertIn('USD', currencies)
        self.assertIn('EUR', currencies)
        self.assertIn('RUB', currencies)
        self.assertIn('CNY', currencies)
        # KZT не в TRACKED_CURRENCIES
        self.assertNotIn('KZT', currencies)

    def test_parse_correct_rates(self):
        result = _parse_nbrk_xml(SAMPLE_NBRK_XML, date(2026, 5, 20))
        usd = next(r for r in result if r['currency'] == 'USD')
        self.assertEqual(usd['rate'], Decimal('475.46'))
        self.assertEqual(usd['source'], 'nbrk')
        self.assertEqual(usd['date'], date(2026, 5, 20))

    def test_parse_invalid_xml_raises(self):
        with self.assertRaises(ValueError):
            _parse_nbrk_xml('<broken xml', date(2026, 5, 20))

    def test_parse_skips_bad_rate(self):
        xml = """<rates><item><title>USD</title><description>N/A</description></item></rates>"""
        result = _parse_nbrk_xml(xml, date(2026, 5, 20))
        self.assertEqual(result, [])


class NbrkFetchTest(TestCase):
    @patch('finances.services.nbrk.requests.get')
    def test_fetch_calls_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_NBRK_XML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_nbrk_rates(date(2026, 5, 20))

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        self.assertIn('20.05.2026', call_url)
        self.assertGreater(len(result), 0)

    @patch('finances.services.nbrk.requests.get')
    def test_fetch_raises_on_http_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.RequestException("timeout")
        with self.assertRaises(req_lib.RequestException):
            fetch_nbrk_rates(date(2026, 5, 20))


class SaveNbrkRatesTest(TestCase):
    def _sample_rates(self):
        return [
            {'currency': 'USD', 'date': date(2026, 5, 20), 'rate': Decimal('475.46'), 'source': 'nbrk'},
            {'currency': 'EUR', 'date': date(2026, 5, 20), 'rate': Decimal('512.30'), 'source': 'nbrk'},
        ]

    def test_save_creates_records(self):
        result = save_nbrk_rates(self._sample_rates())
        self.assertEqual(result['created'], 2)
        self.assertEqual(ExchangeRate.objects.count(), 2)

    def test_save_updates_existing(self):
        ExchangeRate.objects.create(currency='USD', date=date(2026, 5, 20), rate=Decimal('470.00'))
        result = save_nbrk_rates(self._sample_rates())
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(ExchangeRate.objects.get(currency='USD', date=date(2026, 5, 20)).rate, Decimal('475.46'))


class FetchExchangeRatesTaskTest(TestCase):
    @patch('finances.services.nbrk.requests.get')
    def test_task_saves_rates_to_db(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_NBRK_XML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from finances.tasks import fetch_exchange_rates
        result = fetch_exchange_rates(date_str='2026-05-20')

        self.assertIn('created', result)
        self.assertGreater(result['created'], 0)
        self.assertGreater(ExchangeRate.objects.count(), 0)

    @patch('finances.services.nbrk.requests.get')
    def test_task_with_no_date_uses_today(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_NBRK_XML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from finances.tasks import fetch_exchange_rates
        result = fetch_exchange_rates()
        self.assertIn('created', result)


# ── BE-6.4: Аналитика аренды ──────────────────────────────────────────────────

def make_user(role, username=None):
    username = username or f'user_{role}'
    return User.objects.create_user(
        username=username,
        password='pass',
        role=role,
    )


class RentAnalyticsViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.cfo_user = make_user(RoleEnums.CFO.value, 'cfo_rent')
        self.tenant = make_tenant('АренАналитик')
        self.today = date.today()

        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-RA-001',
            period=date(self.today.year, 1, 1),
            charged=Decimal('200000.00'),
            paid=Decimal('150000.00'),
            status=TenantPaymentRegistry.Status.PARTIAL,
        )
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-RA-002',
            period=date(self.today.year, 2, 1),
            charged=Decimal('200000.00'),
            paid=Decimal('200000.00'),
            status=TenantPaymentRegistry.Status.PAID,
        )
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant,
            contract_number='ДОГ-RA-003',
            period=date(self.today.year, 3, 1),
            charged=Decimal('200000.00'),
            paid=Decimal('0.00'),
            balance=Decimal('200000.00'),
            onec_id='ONEC-RA-003',
            status=TenantPaymentRegistry.Status.OVERDUE,
        )

    def _login(self, user):
        self.client.force_login(user)

    def test_rent_analytics_returns_200(self):
        self._login(self.cfo_user)
        response = self.client.get('/finances/analytics/rent/')
        self.assertEqual(response.status_code, 200)

    def test_rent_analytics_context_keys(self):
        self._login(self.cfo_user)
        response = self.client.get('/finances/analytics/rent/')
        self.assertEqual(response.status_code, 200)
        for key in ('top_tenants', 'vacancy_rate', 'avg_rate_per_sqm',
                    'top_debtors', 'rent_dynamics', 'total_revenue_ytd', 'total_overdue'):
            self.assertIn(key, response.context, f'Missing context key: {key}')

    def test_top_tenants_ytd(self):
        self._login(self.cfo_user)
        response = self.client.get('/finances/analytics/rent/')
        top = response.context['top_tenants']
        self.assertGreaterEqual(len(top), 1)
        total = top[0]['total_paid']
        self.assertEqual(total, Decimal('350000.00'))

    def test_top_debtors_overdue(self):
        self._login(self.cfo_user)
        response = self.client.get('/finances/analytics/rent/')
        debtors = response.context['top_debtors']
        self.assertGreaterEqual(len(debtors), 1)

    def test_rent_dynamics_structure(self):
        self._login(self.cfo_user)
        response = self.client.get('/finances/analytics/rent/')
        dynamics = response.context['rent_dynamics']
        self.assertIn('labels', dynamics)
        self.assertIn('actual', dynamics)
        self.assertEqual(len(dynamics['labels']), len(dynamics['actual']))

    def test_403_for_unauthenticated(self):
        response = self.client.get('/finances/analytics/rent/')
        self.assertIn(response.status_code, (302, 403))
