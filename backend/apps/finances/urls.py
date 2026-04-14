from django.urls import path, include
from . import views

urlpatterns = [
    path('registers/', views.payment_reg, name="reg"),
    
    path('calendar', views.calendar, name="calendar"),
    path('calendar/action/<slug:action>/', views.calendar_action, name="calendar_action"),

    path('budget/', views.budget_list, name="budget"),
    path('budget/<int:pk>/', views.budget, name="budget_item"),
    path('budget/create/', views.budget_create, name="budget_create"),
    path('bill/', views.bill, name="bill"),
]