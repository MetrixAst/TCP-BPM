from django.contrib import admin

from .models import ServiceRequest, ServiceRequestHistory


class ServiceRequestHistoryInline(admin.TabularInline):
    model = ServiceRequestHistory
    extra = 0
    readonly_fields = ('user', 'status', 'comment', 'created_at')
    can_delete = False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'category', 'status', 'priority', 'tenant', 'assignee', 'created_at')
    list_filter = ('status', 'category', 'priority')
    search_fields = ('title', 'description', 'room')
    autocomplete_fields = ()
    inlines = [ServiceRequestHistoryInline]
