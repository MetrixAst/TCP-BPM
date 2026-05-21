from rest_framework import serializers

from .models import (
    FinanceItem,
    TenantPaymentRegistry,
    PaymentCalendarEntry,
    GeneratedInvoice,
    GeneratedInvoiceItem,
    BudgetItem,
    BudgetCategory,
)
from .enums import FinanceItemType
class FinanceItemSerializer(serializers.ModelSerializer):

    category = serializers.SerializerMethodField()

    def get_category(self, obj):
        return FinanceItemType.from_value(obj.category)[1]

    class Meta:
        model = FinanceItem
        fields = '__all__'


class TenantPaymentRegistrySerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TenantPaymentRegistry
        fields = (
            'id',
            'tenant',
            'tenant_name',
            'contract_number',
            'period',
            'charged',
            'paid',
            'balance',
            'planned_date',
            'actual_date',
            'overdue_days',
            'status',
            'status_display',
            'onec_id',
            'synced_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class PaymentCalendarEntrySerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PaymentCalendarEntry
        fields = (
            'id',
            'tenant',
            'tenant_name',
            'contract_number',
            'expected_date',
            'expected_amount',
            'actual_amount',
            'actual_date',
            'status',
            'status_display',
            'onec_id',
            'synced_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class GeneratedInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedInvoiceItem
        fields = (
            'id',
            'name',
            'quantity',
            'unit',
            'price',
            'total',
            'vat_rate',
            'vat_amount',
        )
        read_only_fields = ('id', 'total', 'vat_amount')


class GeneratedInvoiceSerializer(serializers.ModelSerializer):
    items = GeneratedInvoiceItemSerializer(many=True, required=False)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True, allow_null=True)
    counterparty_name = serializers.CharField(
        source='counterparty.short_name',
        read_only=True,
        allow_null=True,
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = GeneratedInvoice
        fields = (
            'id',
            'tenant',
            'tenant_name',
            'counterparty',
            'counterparty_name',
            'number',
            'period',
            'contract_number',
            'total_amount',
            'vat_amount',
            'comment',
            'status',
            'status_display',
            'sent_via',
            'sent_at',
            'onec_invoice_number',
            'onec_status',
            'onec_id',
            'synced_at',
            'created_at',
            'updated_at',
            'items',
        )
        read_only_fields = (
            'id',
            'tenant_name',
            'counterparty_name',
            'status_display',
            'onec_invoice_number',
            'onec_status',
            'onec_id',
            'synced_at',
            'created_at',
            'updated_at',
        )

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        invoice = GeneratedInvoice.objects.create(**validated_data)
        for item_data in items_data:
            GeneratedInvoiceItem.objects.create(invoice=invoice, **item_data)
        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                GeneratedInvoiceItem.objects.create(invoice=instance, **item_data)
        return instance


class BudgetCategoryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetCategory
        fields = ('id', 'name', 'category_type', 'code')


class BudgetItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    period_label = serializers.CharField(source='get_period_label', read_only=True)
    category_detail = BudgetCategoryBriefSerializer(source='category', read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('month', 'quarter', 'note'):
            if name in self.fields:
                self.fields[name].required = False
                self.fields[name].allow_null = True

    def to_internal_value(self, data):
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        period_type = mutable.get('period_type', BudgetItem.Period.MONTHLY)
        if period_type == BudgetItem.Period.MONTHLY and 'quarter' not in mutable:
            mutable['quarter'] = None
        if period_type == BudgetItem.Period.QUARTERLY and 'month' not in mutable:
            mutable['month'] = None
        if period_type == BudgetItem.Period.YEARLY:
            mutable.setdefault('month', None)
            mutable.setdefault('quarter', None)
        return super().to_internal_value(mutable)

    class Meta:
        model = BudgetItem
        fields = (
            'id',
            'category',
            'category_name',
            'category_detail',
            'period_type',
            'year',
            'month',
            'quarter',
            'plan',
            'fact',
            'forecast',
            'note',
            'period_label',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'category_name', 'category_detail', 'period_label', 'created_at', 'updated_at')
        extra_kwargs = {
            'month': {'required': False, 'allow_null': True},
            'quarter': {'required': False, 'allow_null': True},
            'note': {'required': False, 'allow_null': True},
        }
