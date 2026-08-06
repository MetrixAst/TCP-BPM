from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from account.models_rbac import AppPermission, PermissionProfile
from account.services.permissions import invalidate_role_cache


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