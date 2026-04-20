from django.urls import path, include
from . import views

urlpatterns = [
    path('structure/', views.structure, name="org"),

    path('employees/', views.employees, name="employees"),
    path('employees/create/', views.create_employee, name="create_employee"),
    path('employee/<int:pk>/', views.edit_employee, name="edit_employee"),

    path('companies/', views.companies, name="companies"),
    path('positions/', views.positions, name="positions"),

    path('calendar/<slug:category>/', views.calendar, name="calendar"),
    path('calendar/<slug:category>/json/', views.calendar_json, name="calendar_json"),
    path('calendar/edit/<int:pk>/', views.edit_calendar_item, name="edit_calendar"),
    path('calendar/delete/<int:pk>/', views.delete_calendar_item, name="delete_calendar"),
    
]