from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from account.models_rbac import AppPermission, PermissionProfile, ProfileAssignment
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