from django.contrib import admin
from .models import Company, Position, Vacation, SickLeave, EmploymentContract

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'bin_number', 'email', 'phone', 'created_at')
    search_fields = ('name', 'bin_number')

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'department')
    list_filter = ('department',)
    search_fields = ('title',)


@admin.register(Vacation)
class VacationAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'status', 'enbek_id')


@admin.register(SickLeave)
class SickLeaveAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'enbek_id')


@admin.register(EmploymentContract)
class EmploymentContractAdmin(admin.ModelAdmin):
    list_display = ('employee', 'number', 'date', 'status', 'enbek_id')