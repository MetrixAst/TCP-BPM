from django.contrib import admin
from .models import Remnant, Invoice, Counterparty, CounterpartyType, InvoiceItem

admin.site.register(Remnant)


@admin.register(CounterpartyType)
class CounterpartyTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'access_scope', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    prepopulated_fields = {'code': ('name',)}


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'bin_number', 'counterparty_type', 'is_supplier', 'is_customer', 'synced_at')
    search_fields = ('short_name', 'full_name', 'bin_number', 'id_1c')
    list_filter = ('is_supplier', 'is_customer', 'counterparty_type')

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1 
    readonly_fields = ['name', 'quantity', 'price', 'total', 'vat_rate', 'vat_amount']
    can_delete = False 

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['number', 'Date', 'counterparty', 'status', 'Sum']
    list_filter = ['status', 'Date']
    search_fields = ['number', 'counterparty__short_name', 'counterparty__bin_number']
    
    readonly_fields = [
        'counterparty', 'number', 'status', 'comment', 
        'Sum', 'Date', 'CounterpartyAccount', 'OrganizationAccount', 'Payment'
    ]
    
    inlines = [InvoiceItemInline] 

    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False 

    def has_change_permission(self, request, obj=None):
        return False 