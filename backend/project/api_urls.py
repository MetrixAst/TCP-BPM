from django.urls import path, include
from rest_framework.routers import DefaultRouter

from tasks.api import TaskViewSet
from hr.api import EmployeeViewSet, DepartmentViewSet, CompanyViewSet
from finances.api import (
    TenantPaymentRegistryViewSet,
    PaymentCalendarEntryViewSet,
    GeneratedInvoiceViewSet,
    BudgetItemViewSet,
)

router = DefaultRouter()
router.register('tasks', TaskViewSet, basename='task')
router.register('hr/employees', EmployeeViewSet, basename='employee')
router.register('hr/departments', DepartmentViewSet, basename='department')
router.register('hr/companies', CompanyViewSet, basename='company')
router.register('finances/payments', TenantPaymentRegistryViewSet, basename='finance-payment')
router.register('finances/calendar', PaymentCalendarEntryViewSet, basename='finance-calendar')
router.register('finances/invoices', GeneratedInvoiceViewSet, basename='finance-invoice')
router.register('finances/budget', BudgetItemViewSet, basename='finance-budget')

urlpatterns = [
    path('', include(router.urls)),
]
