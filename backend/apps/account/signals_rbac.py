from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from account.models_rbac import AppPermission, PermissionProfile, ProfileAssignment, UserPermissionOverride
from account.services.permissions import invalidate_role_cache, invalidate_assignment_cache_for_scope


@receiver(post_save, sender=PermissionProfile)
@receiver(post_delete, sender=PermissionProfile)
def _profile_changed(sender, instance, **kwargs):
    invalidate_role_cache(instance.role)


@receiver(m2m_changed, sender=PermissionProfile.permissions.through)
def _profile_perms_changed(sender, instance, **kwargs):
    invalidate_role_cache(getattr(instance, "role", None))


@receiver(post_save, sender=AppPermission)
@receiver(post_delete, sender=AppPermission)
def _permission_changed(sender, instance, **kwargs):
    invalidate_role_cache(None)


@receiver(post_save, sender=ProfileAssignment)
@receiver(post_delete, sender=ProfileAssignment)
def _assignment_changed(sender, instance, **kwargs):
    scope_id = instance.role if instance.scope_type == ProfileAssignment.SCOPE_ROLE else instance.department_id
    invalidate_assignment_cache_for_scope(instance.scope_type, scope_id)

def _get_ip(request):
    if request is None:
        return None
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@receiver(m2m_changed, sender=PermissionProfile.permissions.through)
def _audit_profile_perms_changed(sender, instance, action, pk_set, **kwargs):
    if action not in ('post_add', 'post_remove'):
        return

    from account.models_rbac import PermissionAuditLog
    log_action = PermissionAuditLog.ACTION_GRANT if action == 'post_add' else PermissionAuditLog.ACTION_REVOKE

    for perm_id in (pk_set or set()):
        try:
            perm = AppPermission.objects.get(pk=perm_id)
        except AppPermission.DoesNotExist:
            continue
        PermissionAuditLog.objects.create(
            action=log_action,
            profile=instance,
            permission_code=perm.code,
        )

@receiver(post_save, sender=UserPermissionOverride)
def _audit_override_saved(sender, instance, created, **kwargs):
    from account.models_rbac import PermissionAuditLog
    log_action = PermissionAuditLog.ACTION_OVERRIDE_ADD if created else PermissionAuditLog.ACTION_OVERRIDE_CHANGE
    before = None if created else {"effect": instance._pre_save_effect}
    after = {"effect": instance.effect, "reason": instance.reason}
    PermissionAuditLog.objects.create(
        action=log_action,
        target_user=instance.user,
        actor=instance.created_by,
        permission_code=instance.permission.code,
        effect=instance.effect,
        reason=instance.reason,
        before=before,
        after=after,
    )


@receiver(post_delete, sender=UserPermissionOverride)
def _audit_override_deleted(sender, instance, **kwargs):
    from account.models_rbac import PermissionAuditLog
    PermissionAuditLog.objects.create(
        action=PermissionAuditLog.ACTION_OVERRIDE_DELETE,
        target_user=instance.user,
        permission_code=instance.permission.code,
        effect=instance.effect,
        before={"effect": instance.effect, "reason": instance.reason},
        after=None,
    )