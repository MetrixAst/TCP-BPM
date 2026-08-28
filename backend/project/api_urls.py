from django.urls import path, include
from rest_framework.routers import DefaultRouter

from tasks.api import TaskViewSet
from hr.api import EmployeeViewSet, DepartmentViewSet, CompanyViewSet, ManualAttendanceViewSet, AttendanceReportViewSet
from finances.api import (
    TenantPaymentRegistryViewSet,
    PaymentCalendarEntryViewSet,
    GeneratedInvoiceViewSet,
    BudgetItemViewSet,
)
from account.api_rbac import (
    AppPermissionCatalogViewSet,
    DelegationViewSet,
    PermissionProfileViewSet,
    ProfileAssignmentViewSet,
    UserPermissionsViewSet,
    PermissionAuditLogViewSet,
    NotificationViewSet,
    TemporaryAccessViewSet
)


router = DefaultRouter()
router.register('tasks', TaskViewSet, basename='task')
router.register('hr/employees', EmployeeViewSet, basename='employee')
router.register('hr/departments', DepartmentViewSet, basename='department')
router.register('hr/companies', CompanyViewSet, basename='company')
router.register('finances/payments', TenantPaymentRegistryViewSet, basename='finance-payment')
router.register('hr/attendance/manual', ManualAttendanceViewSet, basename='manual-attendance')
router.register('hr/attendance/report', AttendanceReportViewSet, basename='attendance-report')
router.register('finances/calendar', PaymentCalendarEntryViewSet, basename='finance-calendar')
router.register('finances/invoices', GeneratedInvoiceViewSet, basename='finance-invoice')
router.register('finances/budget', BudgetItemViewSet, basename='finance-budget')

router.register('permissions/users',    UserPermissionsViewSet,      basename='perm-user')
router.register('permissions/profiles',     PermissionProfileViewSet,    basename='perm-profile')
router.register('permissions/catalog',      AppPermissionCatalogViewSet, basename='perm-catalog')
router.register('permissions/assignments',  ProfileAssignmentViewSet,    basename='perm-assignment')
router.register('permissions/delegate',     DelegationViewSet,           basename='perm-delegate')
router.register('permissions/audit', PermissionAuditLogViewSet, basename='perm-audit')
router.register('notifications', NotificationViewSet, basename='notification')
router.register('permissions/temporary', TemporaryAccessViewSet, basename='temp-access')


urlpatterns = [
    path('', include(router.urls)),
]