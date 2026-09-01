from django.core.cache import cache

from account.role_permissions import RoleEnums, RolePermissions

ROLE_CACHE_PREFIX = "rbac:role:"
ASSIGNMENT_CACHE_PREFIX = "rbac:assignment:user:"
ROLE_CACHE_TTL = 300

EFFECT_ALLOW = "ALLOW"
EFFECT_DENY = "DENY"


def perm_code(permission) -> str:
    if hasattr(permission, "value"):
        return permission.value
    return str(permission)


def role_value(role) -> str | None:
    if role is None:
        return None
    if hasattr(role, "value"):
        return role.value
    return role


def _fallback_role_codes(role: str) -> set:
    return {perm_code(p) for p in RolePermissions.permissions.get(role, [])}


def role_permission_codes(role) -> set:
    role = role_value(role)
    if not role:
        return set()

    key = ROLE_CACHE_PREFIX + role
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        from account.models_rbac import PermissionProfile

        profile = PermissionProfile.objects.get(role=role)
        codes = set(
            profile.permissions.filter(is_active=True).values_list("code", flat=True)
        )
        cache.set(key, codes, ROLE_CACHE_TTL)
        return codes
    except Exception:
        return _fallback_role_codes(role)


def assignment_permission_codes(user) -> set:
    if not getattr(user, "pk", None):
        return set()

    key = ASSIGNMENT_CACHE_PREFIX + str(user.pk)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        from django.db.models import Q
        from account.models_rbac import ProfileAssignment

        role = role_value(getattr(user, "role", None))
        dept_id = None
        try:
            emp = user.employee_info
            dept_id = emp.department_id if emp else None
        except Exception:
            pass

        query = Q()
        if role:
            query |= Q(scope_type=ProfileAssignment.SCOPE_ROLE, role=role)
        if dept_id:
            query |= Q(scope_type=ProfileAssignment.SCOPE_DEPARTMENT, department_id=dept_id)

        if not query:
            cache.set(key, set(), ROLE_CACHE_TTL)
            return set()

        codes = set(
            ProfileAssignment.objects
            .filter(query)
            .values_list("profile__permissions__code", flat=True)
        )
        codes.discard(None)

        cache.set(key, codes, ROLE_CACHE_TTL)
        return codes

    except Exception:
        return set()


def role_has_permission(role, permission) -> bool:
    return perm_code(permission) in role_permission_codes(role)


def user_override_effect(user, permission):
    if not getattr(user, "pk", None):
        return None
    try:
        from account.models_rbac import UserPermissionOverride

        return (
            UserPermissionOverride.objects.filter(
                user_id=user.pk, permission__code=perm_code(permission)
            )
            .values_list("effect", flat=True)
            .first()
        )
    except Exception:
        return None


def user_has_permission(user, permission) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    effect = user_override_effect(user, permission)
    if effect == EFFECT_DENY:
        return False
    if effect == EFFECT_ALLOW:
        return True

    code = perm_code(permission)

    if code in role_permission_codes(getattr(user, "role", None)):
        return True

    if code in assignment_permission_codes(user):
        return True

    from django.utils import timezone
    from account.models_rbac import TemporaryAccess, AppPermission
    try:
        perm_obj = AppPermission.objects.filter(code=code).first()
        if perm_obj and TemporaryAccess.objects.filter(
            user=user,
            permission=perm_obj,
            status=TemporaryAccess.STATUS_ACTIVE,
            date_from__lte=timezone.now(),
            date_to__gte=timezone.now(),
        ).exists():
            return True
    except Exception:
        pass

    return False


def invalidate_role_cache(role=None):
    if role is None:
        for r in (e.value for e in RoleEnums):
            cache.delete(ROLE_CACHE_PREFIX + r)
    else:
        rv = role_value(role)
        if rv:
            cache.delete(ROLE_CACHE_PREFIX + rv)


def invalidate_user_assignment_cache(user_id: int):
    cache.delete(ASSIGNMENT_CACHE_PREFIX + str(user_id))


def invalidate_assignment_cache_for_scope(scope_type: str, scope_id):
    from account.models import UserAccount

    if scope_type == "role":
        users = UserAccount.objects.filter(role=scope_id).values_list("pk", flat=True)
    else:
        users = UserAccount.objects.filter(
            employee_info__department_id=scope_id
        ).values_list("pk", flat=True)

    for uid in users:
        cache.delete(ASSIGNMENT_CACHE_PREFIX + str(uid))