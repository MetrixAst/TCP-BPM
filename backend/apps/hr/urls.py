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
    path('leaves/timeline/', views.leave_timeline, name='leave_timeline'),
    path('leaves/export-excel/', views.leave_export_excel, name='leave_export_excel'),
    path('leaves/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:pk>/reject/', views.leave_reject, name='leave_reject'),
    path('leaves/<int:pk>/cancel/', views.leave_cancel, name='leave_cancel'),

    path('attendance/checkin/', views.attendance_checkin, name='attendance_checkin'),
    path('attendance/my/', views.attendance_my, name='attendance_my'),
    path('attendance/journal/', views.attendance_journal, name='attendance_journal'),

    path('documents/', views.documents_list, name='documents_list'),
    path('documents/create/', views.documents_create, name='documents_create'),
    path('documents/<int:pk>/edit/', views.documents_edit, name='documents_edit'),
    path('documents/<int:pk>/delete/', views.documents_delete, name='documents_delete'),
    path('documents/export/', views.documents_export, name='documents_export'),

    path('permits/', views.permits_list, name='permits_list'),
    path('permits/create/', views.permits_create, name='permits_create'),
    path('permits/<int:pk>/edit/', views.permits_edit, name='permits_edit'),
    path('permits/<int:pk>/delete/', views.permits_delete, name='permits_delete'),
    path('permits/export/', views.permits_export, name='permits_export'),

    path('certifications/', views.certifications_list, name='certifications_list'),
    path('certifications/create/', views.certifications_create, name='certifications_create'),
    path('certifications/<int:pk>/edit/', views.certifications_edit, name='certifications_edit'),
    path('certifications/<int:pk>/delete/', views.certifications_delete, name='certifications_delete'),
    path('certifications/export/', views.certifications_export, name='certifications_export'),
]