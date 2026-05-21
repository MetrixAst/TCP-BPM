from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from datetime import date
from decimal import Decimal

from .models import TenantPaymentRegistry, PaymentCalendarEntry, GeneratedInvoice, GeneratedInvoiceItem
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