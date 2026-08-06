from django.core.cache import cache

from account.role_permissions import RoleEnums, RolePermissions

ROLE_CACHE_PREFIX = "rbac:role:"
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

    return role_has_permission(getattr(user, "role", None), permission)


def invalidate_role_cache(role=None):
    if role is None:
        for r in (e.value for e in RoleEnums):
            cache.delete(ROLE_CACHE_PREFIX + r)
    else:
        rv = role_value(role)
        if rv:
            cache.delete(ROLE_CACHE_PREFIX + rv)