from django.contrib import admin
from .models import Remnant, Invoice, Counterparty

admin.site.register(Remnant)
admin.site.register(Invoice)

@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'bin_number', 'is_supplier', 'is_customer', 'synced_at')
    search_fields = ('short_name', 'full_name', 'bin_number', 'id_1c')
    list_filter = ('is_supplier', 'is_customer')

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
