from rest_framework.permissions import BasePermission, SAFE_METHODS

from .role_permissions import RolePermissions, PermissionEnums, RoleEnums


class HasAppPermission(BasePermission):
    """DRF permission backed by RolePermissions.checkPermission."""

    permission = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        return RolePermissions.checkPermission(role, self.permission)


class HasAnyAppPermission(BasePermission):
    """Allow if user has any of the listed permissions."""

    permissions = ()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        return any(
            RolePermissions.checkPermission(role, perm)
            for perm in self.permissions
        )


class ReadOnlyAppPermission(BasePermission):
    """Safe methods require read_permission; writes require write_permission."""

    read_permission = None
    write_permission = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        if request.method in SAFE_METHODS:
            return RolePermissions.checkPermission(role, self.read_permission)
        return RolePermissions.checkPermission(role, self.write_permission)


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
    """HR: read with HR permission; writes for Administrator or HR_COMPANIES."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if hasattr(role, 'value'):
            role = role.value
        if request.method in SAFE_METHODS:
            return RolePermissions.checkPermission(role, PermissionEnums.HR) or RolePermissions.checkPermission(
                role, PermissionEnums.HR_SELF
            )
        return RolePermissions.checkPermission(role, PermissionEnums.HR_COMPANIES)

class FinanceRegistersReadPermission(HasAppPermission):
    permission = PermissionEnums.FINANCE_REGISTERS


class FinanceInvoicesPermission(ReadOnlyAppPermission):
    read_permission = PermissionEnums.FINANCE_INVOICES
    write_permission = PermissionEnums.FINANCE_INVOICES


class FinanceBudgetPermission(ReadOnlyAppPermission):
    read_permission = PermissionEnums.FINANCE_BUDGET
    write_permission = PermissionEnums.FINANCE_BUDGET


class FinanceBudgetWriteRoles(BasePermission):
    """Budget mutations: CFO, Owner, Administrator only."""

    allowed_roles = (
        RoleEnums.CFO.value,
        RoleEnums.OWNER.value,
        RoleEnums.ADMINISTRATOR.value,
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            role = request.user.role
            if hasattr(role, 'value'):
                role = role.value
            return RolePermissions.checkPermission(role, PermissionEnums.FINANCE_BUDGET)
        return request.user.role in self.allowed_roles
