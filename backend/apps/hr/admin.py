from django.contrib import admin
from .models import (
    Company, Position, WorkCalendar, 
    Vacation, SickLeave, EmploymentContract,
    LeaveRequest, LeaveType, AttendanceRecord, EmployeeDocument, WorkCategory, EmployeeWorkPermit
)
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'bin_number', 'email', 'phone', 'created_at')
    search_fields = ('name', 'bin_number')

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'department')
    list_filter = ('department',)
    search_fields = ('title',)

@admin.register(WorkCalendar)
class WorkCalendarAdmin(admin.ModelAdmin):
    list_display = ('date', 'day_type', 'company', 'year')
    list_filter = ('company', 'year', 'day_type')
    search_fields = ('date',)
    date_hierarchy = 'date'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company')

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_paid', 'max_days_per_year')
    search_fields = ('name',)

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 
        'leave_type', 
        'start_date', 
        'end_date', 
        'working_days_count', 
        'status'
    )
    list_filter = ('status', 'leave_type', 'start_date')
    search_fields = ('employee__user__last_name', 'employee__user__first_name', 'comment')
    readonly_fields = ('working_days_count',)
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('employee', 'leave_type', 'status')
        }),
        ('Период отпуска', {
            'fields': (('start_date', 'end_date'), 'working_days_count')
        }),
        ('Дополнительно', {
            'fields': ('approver', 'comment')
        }),
        ('Синхронизация (Enbek)', {
            'classes': ('collapse',), 
            'fields': ('external_enbek_id', 'sync_status'),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

@admin.register(Vacation)
class VacationAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'status', 'enbek_id')

@admin.register(SickLeave)
class SickLeaveAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'enbek_id')

@admin.register(EmploymentContract)
class EmploymentContractAdmin(admin.ModelAdmin):
    list_display = ('employee', 'number', 'date', 'status', 'enbek_id')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'event_type', 'timestamp', 'ip_address', 'get_photo_preview')
    list_filter = ('event_type', 'timestamp', 'employee')
    search_fields = ('employee__user__last_name', 'ip_address', 'workstation')
    readonly_fields = ('get_photo_preview',)

    def get_photo_preview(self, obj):
        if obj.photo:
            return mark_safe(f'<img src="{obj.photo.url}" width="100" />')
        return "Нет фото"
    
    get_photo_preview.short_description = "Превью фото"

@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ['employee', 'doc_type', 'title', 'version', 'status', 'signed_at', 'expires_at', 'sync_status']
    list_filter = ['doc_type', 'status', 'sync_status']
    search_fields = ['employee__user__username', 'title', 'external_enbek_id']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(WorkCategory)
class WorkCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'risk_level', 'certificate_validity_months') 
    search_fields = ('code', 'name')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('code', 'name', 'name_en', 'category_group', 'risk_level')
        }),
        ('Требования безопасности РК', {
            'fields': (
                ('requires_training', 'requires_medical_exam'),
                ('requires_ptw', 'requires_ppe'),
                ('requires_gas_test', 'requires_supervisor', 'requires_license'),
            )
        }),
        ('Сроки и Нормативы', {
            'fields': ('certificate_validity_months', 'required_ppe', 'related_regulations')
        }),
    )

class StatusFilter(admin.SimpleListFilter):
    title = 'Статус допуска'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Активен'),
            ('expiring', 'Истекает (30 дней)'),
            ('expired', 'Просрочен'),
        )

    def queryset(self, request, queryset):
        from datetime import date, timedelta
        today = date.today()
        thirty_days_later = today + timedelta(days=30)
        
        if self.value() == 'active':
            return queryset.filter(expiry_date__gt=thirty_days_later)
        if self.value() == 'expiring':
            return queryset.filter(expiry_date__lte=thirty_days_later, expiry_date__gte=today)
        if self.value() == 'expired':
            return queryset.filter(expiry_date__lt=today)

@admin.register(EmployeeWorkPermit)
class EmployeeWorkPermitAdmin(admin.ModelAdmin):
    list_display = ('get_employee', 'get_category', 'expiry_date', 'get_status_display')
    
    list_filter = (
        StatusFilter,              
        'category',              
        'employee__department',   
    )

    search_fields = ('employee__user__last_name', 'employee__user__first_name', 'category__name', 'document_number')
    
    list_select_related = ('employee__user', 'category', 'employee__department')

    def get_employee(self, obj):
        return obj.employee
    get_employee.short_description = 'Сотрудник'

    def get_category(self, obj):
        return obj.category.name
    get_category.short_description = 'Категория'

    def get_status_display(self, obj):
        status = obj.status
        colors = {
            'expired': 'red',
            'expiring': 'orange',
            'active': 'green'
        }
        from django.utils.html import format_html
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(status, 'black'),
            obj.status_label
        )
    get_status_display.short_description = 'Статус'