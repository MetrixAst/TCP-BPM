"""Права доступа к HR: сотрудники, карточки, кадровые реестры."""

from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from account.role_permissions import PermissionEnums, RoleEnums, RolePermissions


def _role_value(user):
    role = getattr(user, 'role', None)
    if hasattr(role, 'value'):
        return role.value
    return role


def get_registry_access(user):
    """
    is_hr — HR, админ, бухгалтер (кадровые реестры).
    is_head — руководитель отдела (сотрудники и документы своего отдела).
    """
    employee = getattr(user, 'employee_info', None)
    role = _role_value(user)

    is_hr = (
        getattr(user, 'is_superuser', False)
        or role == RoleEnums.ADMINISTRATOR.value
        or role == RoleEnums.HR.value
        or role == RoleEnums.CHIEF_ACCOUNTANT.value
        or RolePermissions.checkPermission(role, PermissionEnums.HR_REGISTRIES)
    )
    is_head = bool(employee and employee.head)
    return is_hr, is_head, employee


def has_employee_directory_access(user):
    """Список сотрудников, оргструктура, чужие карточки (с учётом отдела у руководителя)."""
    is_hr, is_head, _ = get_registry_access(user)
    return is_hr or is_head


def can_view_employee(user, target_employee):
    """Просмотр карточки сотрудника."""
    is_hr, is_head, curr = get_registry_access(user)
    if is_hr:
        return True
    if curr and curr.pk == target_employee.pk:
        return True
    if is_head and curr and curr.department_id == target_employee.department_id:
        return True
    return False


def filter_by_access(queryset, user, employee_field='employee'):
    is_hr, is_head, employee = get_registry_access(user)
    if is_hr:
        return queryset
    if not employee:
        return queryset.none()
    if is_head:
        return queryset.filter(**{f'{employee_field}__department': employee.department})
    return queryset.filter(**{employee_field: employee})


def need_hr_directory(view_method):
    """Доступ к каталогу сотрудников и оргструктуре (HR, руководители)."""

    def _wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            response = redirect('account:auth')
            response['Location'] += f'?next={request.path}'
            return response
        if has_employee_directory_access(request.user):
            return view_method(request, *args, **kwargs)
        return HttpResponseForbidden('Permission Denied')

    _wrapper.__doc__ = view_method.__doc__
    _wrapper.__name__ = view_method.__name__
    return _wrapper


def need_hr_registry(view_method):
    """Кадровые реестры: документы, допуски, сертификации (HR, админ, бухгалтер, руководитель отдела)."""
    def _wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            response = redirect('account:auth')
            response['Location'] += f'?next={request.path}'
            return response
        is_hr, is_head, _ = get_registry_access(request.user)
        if is_hr or is_head:
            return view_method(request, *args, **kwargs)
        return HttpResponseForbidden('Permission Denied')
    _wrapper.__doc__ = view_method.__doc__
    _wrapper.__name__ = view_method.__name__
    return _wrapper