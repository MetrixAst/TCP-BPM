from django.contrib import admin

from .models import TenantPaymentRegistry

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
