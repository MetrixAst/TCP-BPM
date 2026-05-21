from django_filters import rest_framework as filters
from rest_framework import viewsets

from account.drf_permissions import (
    FinanceRegistersReadPermission,
    FinanceInvoicesPermission,
    FinanceBudgetPermission,
    FinanceBudgetWriteRoles,
)
from .models import (
    TenantPaymentRegistry,
    PaymentCalendarEntry,
    GeneratedInvoice,
    BudgetItem,
)
from .serializers import (
    TenantPaymentRegistrySerializer,
    PaymentCalendarEntrySerializer,
    GeneratedInvoiceSerializer,
    BudgetItemSerializer,
)


class TenantPaymentRegistryFilter(filters.FilterSet):
    tenant = filters.NumberFilter(field_name='tenant_id')
    status = filters.CharFilter(field_name='status')
    period = filters.DateFilter(field_name='period')
    period_after = filters.DateFilter(field_name='period', lookup_expr='gte')
    period_before = filters.DateFilter(field_name='period', lookup_expr='lte')

    class Meta:
        model = TenantPaymentRegistry
        fields = ['tenant', 'status', 'period']


class PaymentCalendarEntryFilter(filters.FilterSet):
    tenant = filters.NumberFilter(field_name='tenant_id')
    status = filters.CharFilter(field_name='status')
    expected_date = filters.DateFilter(field_name='expected_date')
    expected_date_after = filters.DateFilter(field_name='expected_date', lookup_expr='gte')
    expected_date_before = filters.DateFilter(field_name='expected_date', lookup_expr='lte')

    class Meta:
        model = PaymentCalendarEntry
        fields = ['tenant', 'status', 'expected_date']


class GeneratedInvoiceFilter(filters.FilterSet):
    tenant = filters.NumberFilter(field_name='tenant_id')
    status = filters.CharFilter(field_name='status')
    period = filters.DateFilter(field_name='period')

    class Meta:
        model = GeneratedInvoice
        fields = ['tenant', 'status', 'period']


class BudgetItemFilter(filters.FilterSet):
    category = filters.NumberFilter(field_name='category_id')
    year = filters.NumberFilter(field_name='year')
    month = filters.NumberFilter(field_name='month')
    period_type = filters.CharFilter(field_name='period_type')

    class Meta:
        model = BudgetItem
        fields = ['category', 'year', 'month', 'period_type']


class TenantPaymentRegistryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TenantPaymentRegistry.objects.select_related('tenant').order_by('-period')
    serializer_class = TenantPaymentRegistrySerializer
    permission_classes = [FinanceRegistersReadPermission]
    filterset_class = TenantPaymentRegistryFilter
    search_fields = ['contract_number', 'tenant__name']
    ordering_fields = ['period', 'status', 'balance', 'created_at']
    ordering = ['-period']


class PaymentCalendarEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentCalendarEntry.objects.select_related('tenant').order_by('expected_date')
    serializer_class = PaymentCalendarEntrySerializer
    permission_classes = [FinanceRegistersReadPermission]
    filterset_class = PaymentCalendarEntryFilter
    search_fields = ['contract_number', 'tenant__name']
    ordering_fields = ['expected_date', 'status', 'expected_amount']
    ordering = ['expected_date']


class GeneratedInvoiceViewSet(viewsets.ModelViewSet):
    queryset = GeneratedInvoice.objects.select_related(
        'tenant',
        'counterparty',
    ).prefetch_related('items').order_by('-created_at')
    serializer_class = GeneratedInvoiceSerializer
    permission_classes = [FinanceInvoicesPermission]
    filterset_class = GeneratedInvoiceFilter
    search_fields = ['number', 'contract_number', 'tenant__name']
    ordering_fields = ['created_at', 'period', 'status', 'total_amount']
    ordering = ['-created_at']


class BudgetItemViewSet(viewsets.ModelViewSet):
    queryset = BudgetItem.objects.select_related('category').order_by('-year', '-month')
    serializer_class = BudgetItemSerializer
    permission_classes = [FinanceBudgetWriteRoles]
    filterset_class = BudgetItemFilter
    search_fields = ['category__name', 'note']
    ordering_fields = ['year', 'month', 'plan', 'fact']
    ordering = ['-year', '-month']
