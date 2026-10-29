"""
Кто что видит в планах отделов:

- право «Планы: все отделы» (директор, собственник, администратор) — все планы;
- руководитель отдела — планы своего отдела и подотделов, может их составлять;
- сотрудник отдела — план своего отдела; ответственный за пункт — меняет его статус и результат.
"""

from account.role_permissions import PermissionEnums, RoleEnums
from account.services.permissions import user_has_permission


def can_view_all(user):
    return user.is_superuser or user_has_permission(user, PermissionEnums.PLANS_VIEW_ALL)


def is_plans_admin(user):
    role = getattr(user, 'role', None)
    if hasattr(role, 'value'):
        role = role.value
    return user.is_superuser or role == RoleEnums.ADMINISTRATOR.value


def managed_department_ids(user):
    employee = getattr(user, 'employee_info', None)
    if not employee or not employee.head or not employee.department_id:
        return []
    return list(employee.department.get_descendants(include_self=True).values_list('id', flat=True))


def own_department_id(user):
    employee = getattr(user, 'employee_info', None)
    return employee.department_id if employee else None


def can_edit_plan(user, plan):
    return is_plans_admin(user) or plan.department_id in managed_department_ids(user)


def can_view_plan(user, plan):
    return (
        can_view_all(user)
        or can_edit_plan(user, plan)
        or plan.department_id == own_department_id(user)
        or plan.items.filter(responsible=user).exists()
    )


def can_update_item(user, item):
    return can_edit_plan(user, item.plan) or item.responsible_id == user.id


def creatable_departments(user):
    from account.models import Department

    if is_plans_admin(user):
        return Department.objects.order_by('name')
    return Department.objects.filter(pk__in=managed_department_ids(user)).order_by('name')


def has_plans_access(user):
    from .models import PlanItem

    return bool(
        can_view_all(user)
        or is_plans_admin(user)
        or managed_department_ids(user)
        or own_department_id(user)
        or PlanItem.objects.filter(responsible=user).exists()
    )
