# backend/apps/onec/urls.py
from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

app_name = 'onec'

router = DefaultRouter()
router.register(r'counterparties', views.CounterpartyViewSet, basename='api_counterparty')
router.register(r'invoices', views.InvoiceViewSet, basename='api_invoice')

urlpatterns = [
    path('api/', include(router.urls)),

    path('counterparties/', views.CounterpartyListView.as_view(), name='counterparty_list'),
    path('counterparties/create/', views.counterparty_create, name='counterparty_create'),
    path('counterparties/<int:pk>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparties/sync/', views.counterparty_sync, name='counterparty_sync'),
    path('counterparties/seed-demo/', views.counterparty_seed_demo, name='counterparty_seed_demo'),
    path('counterparties/<int:pk>/', views.CounterpartyDetailView.as_view(), name='counterparty_detail'),
    path('api/cp-search/', views.counterparty_search_api, name='counterparty_search_api'),
    path('invoice/create/', views.InvoiceCreateView.as_view(), name='invoice_create'),
]