from django.contrib import admin
from .models import Company, Position, WorkCalendar

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