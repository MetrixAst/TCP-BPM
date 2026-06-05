from account.models import Notification, UserAccount
from account.role_permissions import RoleEnums, RolePermissions, PermissionEnums


def _operations_recipients():
    """Пользователи эксплуатации и администраторы для уведомлений по заявкам."""
    admin_ids = list(
        UserAccount.objects.filter(role=RoleEnums.ADMINISTRATOR.value).values_list('pk', flat=True)
    )
    ecopark_ids = [
        user.pk
        for user in UserAccount.objects.exclude(role__in=RoleEnums.portal_roles())
        if RolePermissions.checkPermission(user.role, PermissionEnums.ECOPARK)
    ]
    recipient_ids = set(admin_ids + ecopark_ids)
    return UserAccount.objects.filter(pk__in=recipient_ids)


def notify_requisition_status(requisition, old_status=None):
    from .enums import RequstionStatusEnum, RequstionTypesEnum

    status_title = requisition.get_status_display()
    text = (
        f'Заявка №{requisition.id} ({requisition.get_requistion_type_display()}): '
        f'{status_title}'
    )

    recipient_ids = set()

    if requisition.user_id:
        recipient_ids.add(requisition.user_id)

    recipient_ids.update(requisition.coordinators.values_list('pk', flat=True))
    recipient_ids.update(requisition.observers.values_list('pk', flat=True))

    if requisition.status in (
        RequstionStatusEnum.COORDINATION.value[0],
        RequstionStatusEnum.SIGNING.value[0],
    ):
        recipient_ids.update(_operations_recipients().values_list('pk', flat=True))

    if (
        requisition.requistion_type == RequstionTypesEnum.WORKS.value[0]
        and requisition.status == RequstionStatusEnum.COORDINATION.value[0]
    ):
        recipient_ids.update(_operations_recipients().values_list('pk', flat=True))

    recipient_ids.discard(None)
    if not recipient_ids:
        return

    notification = Notification.objects.create(
        title=f'Заявка №{requisition.id}',
        text=text,
        target_id=requisition.id,
        target_type='requistion',
    )
    notification.users.add(*UserAccount.objects.filter(pk__in=recipient_ids))
