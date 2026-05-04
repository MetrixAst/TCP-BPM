from django.urls import path
from . import views

app_name = 'hr'

urlpatterns = [
    path('structure/', views.structure, name="org"),
    path('employees/', views.employees, name="employees"),
    path('employees/create/', views.create_employee, name="create_employee"),
    path('employee/<int:pk>/', views.edit_employee, name="edit_employee"),

    path('companies/', views.companies, name="companies"),
    path('positions/', views.positions, name="positions"),

    path('vacations/', views.vacations, name="vacations"),
    path('sick-leaves/', views.sick_leaves, name="sick_leaves"),
    path('contracts/', views.contracts, name="contracts"),

    path('calendar/<slug:category>/', views.calendar, name="calendar"),
    path('calendar/<slug:category>/json/', views.calendar_json, name="calendar_json"),
    path('calendar/edit/<int:pk>/', views.edit_calendar_item, name="edit_calendar"),
    path('calendar/delete/<int:pk>/', views.delete_calendar_item, name="delete_calendar"),

    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/create/', views.leave_create, name='leave_create'),
    path('leaves/ajax-calculate/', views.ajax_calculate_days, name='ajax_calculate_days'),
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/create/', views.leave_create, name='leave_create'),
    path('leaves/ajax-calculate/', views.ajax_calculate_days, name='ajax_calculate_days'),
    path('leaves/timeline/', views.leave_timeline, name='leave_timeline'),
    path('leaves/export-excel/', views.leave_export_excel, name='leave_export_excel'),
    path('leaves/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leaves/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:pk>/reject/', views.leave_reject, name='leave_reject'),
    path('leaves/<int:pk>/cancel/', views.leave_cancel, name='leave_cancel'),
]