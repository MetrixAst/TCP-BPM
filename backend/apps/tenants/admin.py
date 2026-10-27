from django.contrib import admin
from .models import Room, Tenant, TenantCategory, TenantDocument

admin.site.register(TenantCategory)


@admin.register(Room)
class RoomA(admin.ModelAdmin):
    list_display = ('number', 'floor', 'map_id')
    search_fields = ('number', )


@admin.register(Tenant)
class TenantA(admin.ModelAdmin):
    list_display = ('name', 'room', 'note')
    search_fields = ('name', 'email')
    autocomplete_fields = ('room', )


@admin.register(TenantDocument)
class TenantDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'created_at', 'uploaded_by')
    list_filter = ('created_at',)
    search_fields = ('title', 'tenant__name')
    raw_id_fields = ('tenant', 'uploaded_by')
