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

    path('payment-calendar/', views.payment_calendar, name='payment_calendar'),
    path('payment-calendar/<int:year>/<int:month>/<int:day>/', views.payment_calendar_day, name='payment_calendar_day'),

   
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<int:pk>/send/', views.invoice_send, name='invoice_send'),
    path('invoices/<int:pk>/viewed/', views.invoice_mark_viewed, name='invoice_mark_viewed'),
    path('invoices/<int:pk>/paid/', views.invoice_mark_paid, name='invoice_mark_paid'),
    path('invoices/<int:pk>/cancel/', views.invoice_cancel, name='invoice_cancel'),
]