from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'action',
        'object_type',
        'object_id',
        'user',
        'ip_address',
    )
    list_filter = ('action', 'object_type', 'created_at')
    search_fields = ('object_repr', 'object_id', 'user__username')
    readonly_fields = (
        'user',
        'action',
        'object_type',
        'object_id',
        'object_repr',
        'changes',
        'ip_address',
        'user_agent',
        'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
