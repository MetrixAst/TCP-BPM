from django.contrib import admin

from .models import TenantPaymentRegistry
from .models import PaymentCalendarEntry

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
