from rest_framework.permissions import BasePermission, SAFE_METHODS

from .role_permissions import RolePermissions, PermissionEnums, RoleEnums
from .services.permissions import user_has_permission


class HasAppPermission(BasePermission):

    permission = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_has_permission(request.user, self.permission)


class HasAnyAppPermission(BasePermission):

    permissions = ()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return any(
            user_has_permission(request.user, perm)
            for perm in self.permissions
        )


class ReadOnlyAppPermission(BasePermission):

    read_permission = None
    write_permission = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return user_has_permission(request.user, self.read_permission)
        return user_has_permission(request.user, self.write_permission)


class TasksPermission(HasAppPermission):
    permission = PermissionEnums.TASKS


class HrReadPermission(HasAppPermission):
    permission = PermissionEnums.HR


class HrWritePermission(HasAnyAppPermission):
    permissions = (
        PermissionEnums.HR_COMPANIES,
        PermissionEnums.USERS_LIST,
    )


class HrApiPermission(BasePermission):

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return user_has_permission(request.user, PermissionEnums.HR)
        return user_has_permission(request.user, PermissionEnums.HR_COMPANIES)


class FinanceRegistersReadPermission(HasAppPermission):
    permission = PermissionEnums.FINANCE_REGISTERS


class FinanceInvoicesPermission(ReadOnlyAppPermission):
    read_permission = PermissionEnums.FINANCE_INVOICES
    write_permission = PermissionEnums.FINANCE_INVOICES


class FinanceBudgetPermission(ReadOnlyAppPermission):
    read_permission = PermissionEnums.FINANCE_BUDGET
    write_permission = PermissionEnums.FINANCE_BUDGET


class FinanceBudgetWriteRoles(BasePermission):

    allowed_roles = (
        RoleEnums.CFO.value,
        RoleEnums.OWNER.value,
        RoleEnums.ADMINISTRATOR.value,
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return user_has_permission(request.user, PermissionEnums.FINANCE_BUDGET)
        if getattr(request.user, 'is_superuser', False):
            return True
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        return role in self.allowed_roles

class HROrAdminPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        return role in (RoleEnums.ADMINISTRATOR.value, RoleEnums.HR.value)

class AttendanceRegistryPermission(BasePermission):
    ALLOWED_ROLES = {'administrator', 'hr', 'owner'}

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        if role in self.ALLOWED_ROLES:
            return True

        employee = getattr(request.user, 'employee_info', None)
        if employee and getattr(employee, 'head', False):
            return True
        return False
