# backend/apps/onec/urls.py
from django.urls import path
from . import views

app_name = 'onec'

urlpatterns = [
    path('counterparties/', views.CounterpartyListView.as_view(), name='counterparty_list'),
    path('counterparties/<int:pk>/', views.CounterpartyDetailView.as_view(), name='counterparty_detail'),
    path('api/cp-search/', views.counterparty_search_api, name='counterparty_search_api'),
    path('invoice/create/', views.InvoiceCreateView.as_view(), name='invoice_create'),
]