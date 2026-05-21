from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from account.models import Employee
from finances.models import BudgetItem, GeneratedInvoice
from hr.models import LeaveRequest

from .models import AuditLog
from .services import (
    cache_pre_save_instance,
    diff_instances,
    log_event,
    pop_cached_instance,
)


def _register_model(model, track_fields=None):
    @receiver(pre_save, sender=model)
    def _pre_save(sender, instance, **kwargs):
        cache_pre_save_instance(instance)

    @receiver(post_save, sender=model)
    def _post_save(sender, instance, created, **kwargs):
        if created:
            log_event(AuditLog.Action.CREATE, instance=instance)
            return
        old = pop_cached_instance(instance)
        if old is None:
            return
        changes = diff_instances(old, instance, field_names=track_fields)
        if changes:
            log_event(AuditLog.Action.UPDATE, instance=instance, changes=changes)

    @receiver(pre_delete, sender=model)
    def _pre_delete(sender, instance, **kwargs):
        pop_cached_instance(instance)
        log_event(AuditLog.Action.DELETE, instance=instance)


_register_model(GeneratedInvoice)
_register_model(BudgetItem)
_register_model(Employee)
_register_model(
    LeaveRequest,
    track_fields=['status', 'start_date', 'end_date', 'comment', 'approver_id', 'leave_type_id'],
)


@receiver(user_logged_in)
def audit_user_login(sender, request, user, **kwargs):
    log_event(
        AuditLog.Action.LOGIN,
        object_type='UserAccount',
        object_id=str(user.pk),
        object_repr=user.get_name,
        user=user,
    )
