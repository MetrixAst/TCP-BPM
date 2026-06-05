from account.models import Notification, UserAccount
from account.role_permissions import RoleEnums, RolePermissions, PermissionEnums


def _manager_recipients():
    """Сотрудники, обрабатывающие сервисные заявки (не портальные)."""
    ids = [
        user.pk
        for user in UserAccount.objects.exclude(role__in=RoleEnums.portal_roles())
        if RolePermissions.checkPermission(user.role, PermissionEnums.SERVICE_REQUESTS)
    ]
    return UserAccount.objects.filter(pk__in=ids)


def _push(title, text, ticket, recipient_ids):
    recipient_ids = {pk for pk in recipient_ids if pk}
    if not recipient_ids:
        return
    notification = Notification.objects.create(
        title=title,
        text=text[:300],
        target_id=ticket.id,
        target_type='ticket',
    )
    notification.users.add(*UserAccount.objects.filter(pk__in=recipient_ids))


def notify_ticket_created(ticket):
    """Новая заявка — уведомляем обрабатывающих сотрудников."""
    recipients = set(_manager_recipients().values_list('pk', flat=True))
    _push(
        f'Новая заявка {ticket.number}',
        f'{ticket.get_category_display()}: {ticket.title}',
        ticket,
        recipients,
    )


def notify_ticket_status(ticket, actor=None):
    """Смена статуса — уведомляем заявителя, ответственного и обрабатывающих."""
    recipients = set()
    if ticket.author_id:
        recipients.add(ticket.author_id)
    if ticket.assignee_id:
        recipients.add(ticket.assignee_id)
    recipients.update(_manager_recipients().values_list('pk', flat=True))
    if actor is not None:
        recipients.discard(actor.id)
    _push(
        f'Заявка {ticket.number}: {ticket.get_status_display()}',
        f'{ticket.title} — статус «{ticket.get_status_display()}».',
        ticket,
        recipients,
    )


def notify_ticket_assigned(ticket, actor=None):
    """Маршрутизация — уведомляем ответственного и заявителя."""
    recipients = set()
    if ticket.assignee_id:
        recipients.add(ticket.assignee_id)
    if ticket.author_id:
        recipients.add(ticket.author_id)
    if actor is not None:
        recipients.discard(actor.id)
    dept = ticket.department.name if ticket.department else '—'
    _push(
        f'Заявка {ticket.number} назначена',
        f'{ticket.title} — отдел «{dept}».',
        ticket,
        recipients,
    )
