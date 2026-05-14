from django.contrib import admin

from .models import TenantPaymentRegistry, GeneratedInvoice, GeneratedInvoiceItem, PaymentCalendarEntry


@admin.register(TenantPaymentRegistry)
class TenantPaymentRegistryAdmin(admin.ModelAdmin):
    list_display  = (
        'tenant', 'contract_number', 'period',
        'charged', 'paid', 'balance',
        'planned_date', 'actual_date',
        'overdue_days', 'status', 'onec_id', 'synced_at',
    )
    list_filter   = ('status', 'period', 'tenant__category')
    search_fields = ('tenant__name', 'contract_number', 'onec_id')
    date_hierarchy = 'period'
    ordering      = ('-period', 'tenant')
    readonly_fields = (
        'onec_id', 'synced_at', 'created_at', 'updated_at', 'balance',
    )

    fieldsets = (
        ('Арендатор', {
            'fields': ('tenant', 'contract_number', 'period'),
        }),
        ('Суммы', {
            'fields': ('charged', 'paid', 'balance'),
        }),
        ('Даты', {
            'fields': ('planned_date', 'actual_date', 'overdue_days'),
        }),
        ('Статус', {
            'fields': ('status',),
        }),
        ('1С / Синхронизация', {
            'fields': ('onec_id', 'synced_at', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False   

    def has_delete_permission(self, request, obj=None):
        return False   

@admin.register(PaymentCalendarEntry)
class PaymentCalendarEntryAdmin(admin.ModelAdmin):
    list_display = (
        'tenant', 'contract_number',
        'expected_date', 'expected_amount',
        'actual_date', 'actual_amount',
        'status', 'onec_id', 'synced_at',
    )
    list_filter   = ('status', 'expected_date', 'tenant__category')
    search_fields = ('tenant__name', 'contract_number', 'onec_id')
    date_hierarchy = 'expected_date'
    ordering      = ('expected_date', 'tenant')
    readonly_fields = ('onec_id', 'synced_at', 'created_at', 'updated_at')

    fieldsets = (
        ('Арендатор', {
            'fields': ('tenant', 'contract_number'),
        }),
        ('План', {
            'fields': ('expected_date', 'expected_amount'),
        }),
        ('Факт', {
            'fields': ('actual_date', 'actual_amount'),
        }),
        ('Статус', {
            'fields': ('status',),
        }),
        ('1С / Синхронизация', {
            'fields': ('onec_id', 'synced_at', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

class GeneratedInvoiceItemInline(admin.TabularInline):
    model  = GeneratedInvoiceItem
    extra  = 0
    readonly_fields = ('total', 'vat_amount')
    fields = ('name', 'quantity', 'unit', 'price', 'vat_rate', 'total', 'vat_amount')


@admin.register(GeneratedInvoice)
class GeneratedInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'tenant', 'counterparty',
        'period', 'total_amount', 'vat_amount',
        'status', 'sent_via', 'sent_at',
        'onec_invoice_number', 'onec_status',
    )
    list_filter   = ('status', 'sent_via', 'period')
    search_fields = ('number', 'tenant__name', 'counterparty__short_name', 'onec_invoice_number')
    date_hierarchy = 'created_at'
    readonly_fields = ('onec_id', 'onec_invoice_number', 'onec_status', 'synced_at', 'created_at', 'updated_at')
    inlines = [GeneratedInvoiceItemInline]

    fieldsets = (
        ('Основное', {
            'fields': ('number', 'period', 'contract_number', 'tenant', 'counterparty', 'comment'),
        }),
        ('Суммы', {
            'fields': ('total_amount', 'vat_amount'),
        }),
        ('Статус и отправка', {
            'fields': ('status', 'sent_via', 'sent_at'),
        }),
        ('1С', {
            'fields': ('onec_invoice_number', 'onec_status', 'onec_id', 'synced_at'),
            'classes': ('collapse',),
        }),
        ('Служебные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
