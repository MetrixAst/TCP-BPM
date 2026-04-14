from django.contrib import admin
from .models import Room, Tenant, TenantCategory

admin.site.register(TenantCategory)


@admin.register(Room)
class RoomA(admin.ModelAdmin):
    list_display = ('number', 'floor', 'map_id')
    search_fields = ('number', )


@admin.register(Tenant)
class TenantA(admin.ModelAdmin):
    list_display = ('name', 'room', 'note')
    autocomplete_fields = ('room', )
