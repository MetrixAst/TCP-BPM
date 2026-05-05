from django.contrib import admin
from .models import (
    Company, Position, WorkCalendar, 
    Vacation, SickLeave, EmploymentContract,
    LeaveRequest, LeaveType
)

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