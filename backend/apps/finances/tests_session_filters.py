from datetime import date
from decimal import Decimal

from django.test import TestCase

from finances.models import PaymentCalendarEntry, TenantPaymentRegistry
from finances.services.session_filters import (
    filter_registry,
    get_filters,
)
from finances.tests import make_tenant


class SessionFiltersServiceTest(TestCase):

    def setUp(self):
        self.tenant_a = make_tenant('ФильтрА')
        self.tenant_b = make_tenant('ФильтрБ')
        period = date(2026, 5, 1)
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant_a,
            contract_number='A-1',
            period=period,
            paid=Decimal('100'),
            charged=Decimal('100'),
        )
        TenantPaymentRegistry.objects.create(
            tenant=self.tenant_b,
            contract_number='B-1',
            period=period,
            paid=Decimal('500'),
            charged=Decimal('500'),
        )

    def test_filter_registry_by_tenant(self):
        qs = filter_registry(TenantPaymentRegistry.objects.all(), {
            'tenant': str(self.tenant_a.pk),
        })
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().paid, Decimal('100'))

    def test_get_filters_empty_without_request(self):
        self.assertEqual(get_filters(None), {})
