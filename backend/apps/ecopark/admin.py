from django.contrib import admin
from .models import (
    EcoObject, EcoExecutor, EcoWork,
    RoundPoint, ChecklistTemplate, ChecklistItem,
    RoundVisit, RoundVisitAnswer, Defect,
)

admin.site.register(EcoObject)
admin.site.register(EcoExecutor)
admin.site.register(EcoWork)


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 1


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_by', 'created_at')
    inlines = [ChecklistItemInline]


@admin.register(RoundPoint)
class RoundPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'checklist', 'is_active', 'check_interval_hours', 'created_at')
    list_filter = ('is_active', 'checklist')


class RoundVisitAnswerInline(admin.TabularInline):
    model = RoundVisitAnswer
    extra = 0
    readonly_fields = ('item', 'passed', 'comment', 'photo')


@admin.register(RoundVisit)
class RoundVisitAdmin(admin.ModelAdmin):
    list_display = ('point', 'employee', 'created_at', 'has_failed_items')
    list_filter = ('point',)
    inlines = [RoundVisitAnswerInline]


@admin.register(Defect)
class DefectAdmin(admin.ModelAdmin):
    list_display = ('point', 'description', 'status', 'reported_by', 'resolved_by', 'created_at')
    list_filter = ('status', 'point')