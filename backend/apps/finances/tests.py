from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from datetime import date
from decimal import Decimal

from .models import TenantPaymentRegistry
from tenants.models import Tenant, TenantCategory, Room

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