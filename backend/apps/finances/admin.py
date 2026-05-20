from django.contrib import admin

from .models import TenantPaymentRegistry, GeneratedInvoice, GeneratedInvoiceItem, PaymentCalendarEntry, BudgetCategory, BudgetItem, FinancialStatement, CashFlowRecord

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


@admin.register(BudgetCategory)
class BudgetCategoryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'category_type', 'parent', 'code', 'order', 'is_active')
    list_filter   = ('category_type', 'is_active', 'parent')
    search_fields = ('name', 'code')
    ordering      = ('category_type', 'order', 'name')
    fieldsets = (
        ('Основное', {
            'fields': ('name', 'category_type', 'parent', 'code', 'order', 'is_active'),
        }),
        ('Дополнительно', {
            'fields': ('description',),
            'classes': ('collapse',),
        }),
    )


@admin.register(BudgetItem)
class BudgetItemAdmin(admin.ModelAdmin):
    list_display  = (
        'category', 'period_type', 'year', 'month', 'quarter',
        'plan', 'fact', 'forecast', 'variance', 'execution_pct',
    )
    list_filter   = ('period_type', 'year', 'category__category_type')
    search_fields = ('category__name', 'note')
    ordering      = ('year', 'month', 'quarter', 'category')
    readonly_fields = ('variance', 'variance_pct', 'execution_pct', 'created_at', 'updated_at')
    fieldsets = (
        ('Категория и период', {
            'fields': ('category', 'period_type', 'year', 'month', 'quarter'),
        }),
        ('Суммы', {
            'fields': ('plan', 'fact', 'forecast'),
        }),
        ('Аналитика', {
            'fields': ('variance', 'variance_pct', 'execution_pct'),
        }),
        ('Прочее', {
            'fields': ('note', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

@admin.register(FinancialStatement)
class FinancialStatementAdmin(admin.ModelAdmin):
    list_display = (
        '__str__', 'period_type', 'year', 'month', 'quarter',
        'revenue_fact', 'ebitda_fact', 'net_profit_fact',
        'ebitda_margin_fact', 'net_margin_fact',
    )
    list_filter   = ('period_type', 'year')
    search_fields = ('note',)
    readonly_fields = (
        'ebitda_margin_fact', 'net_margin_fact', 'operating_margin_fact',
        'revenue_variance', 'net_profit_variance', 'ebitda_variance',
        'created_at', 'updated_at',
    )
    filter_horizontal = ('revenue_categories', 'expense_categories')
    fieldsets = (
        ('Период', {
            'fields': ('period_type', 'year', 'month', 'quarter'),
        }),
        ('Выручка (Revenue)', {
            'fields': ('revenue_plan', 'revenue_fact', 'revenue_forecast', 'revenue_variance'),
        }),
        ('EBITDA', {
            'fields': ('ebitda_plan', 'ebitda_fact', 'ebitda_forecast', 'ebitda_variance', 'ebitda_margin_fact'),
        }),
        ('Операционная прибыль', {
            'fields': ('operating_profit_plan', 'operating_profit_fact', 'operating_margin_fact'),
        }),
        ('Чистая прибыль (Net profit)', {
            'fields': ('net_profit_plan', 'net_profit_fact', 'net_profit_forecast', 'net_profit_variance', 'net_margin_fact'),
        }),
        ('Drill-down категории', {
            'fields': ('revenue_categories', 'expense_categories'),
            'classes': ('collapse',),
        }),
        ('Прочее', {
            'fields': ('note', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(CashFlowRecord)
class CashFlowRecordAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_date', 'direction', 'flow_type',
        'amount', 'currency', 'counterparty',
        'budget_category', 'document_number', 'onec_id',
    )
    list_filter  = ('direction', 'flow_type', 'currency', 'transaction_date')
    search_fields = (
        'description', 'document_number',
        'counterparty__short_name', 'onec_id',
    )
    date_hierarchy = 'transaction_date'
    readonly_fields = (
        'onec_id', 'onec_document_type', 'synced_at',
        'created_at', 'updated_at', 'is_inflow', 'is_outflow',
    )
    fieldsets = (
        ('Операция', {
            'fields': (
                'direction', 'flow_type', 'amount', 'currency',
                'transaction_date', 'value_date',
            ),
        }),
        ('Описание', {
            'fields': ('description', 'document_number', 'bank_account'),
        }),
        ('Связи', {
            'fields': ('counterparty', 'budget_category'),
        }),
        ('1С', {
            'fields': ('onec_id', 'onec_document_type', 'synced_at'),
            'classes': ('collapse',),
        }),
        ('Служебные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False  