from django.contrib import admin

from .models import DepartmentPlan, PlanItem


class PlanItemInline(admin.TabularInline):
    model = PlanItem
    extra = 0
    fields = ['title', 'responsible', 'deadline', 'status', 'result', 'task']
    raw_id_fields = ['responsible', 'task']


@admin.register(DepartmentPlan)
class DepartmentPlanAdmin(admin.ModelAdmin):
    list_display = ['department', 'month', 'author', 'updated_at']
    list_filter = ['month', 'department']
    inlines = [PlanItemInline]
