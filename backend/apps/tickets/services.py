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

def get_approver(user):
    from account.models import Employee

    employee = getattr(user, 'employee_info', None)
    if employee and employee.department_id:
        head = Employee.objects.filter(
            department_id=employee.department_id,
            head=True,
            status='active',
        ).exclude(user_id=user.id).select_related('user').first()
        if head:
            return head.user

    admin = UserAccount.objects.filter(role=RoleEnums.ADMINISTRATOR.value).first()
    return admin


def can_bypass_approval(user):
    from account.models import Employee

    if user.role == RoleEnums.ADMINISTRATOR.value:
        return True

    employee = getattr(user, 'employee_info', None)
    if employee and getattr(employee, 'head', False):
        return True

    return False


def notify_approval_requested(ticket, approver):
    if not approver:
        return
    _push(
        f'Заявка {ticket.number} ожидает согласования',
        f'Заявка «{ticket.title}» направлена вам на согласование.',
        ticket,
        {approver.id},
    )


def notify_approval_decision(ticket, decision, actor=None):
    decision_text = 'согласована' if decision == 'approve' else 'отклонена'
    recipients = set()
    if ticket.author_id:
        recipients.add(ticket.author_id)
    if actor:
        recipients.discard(actor.id)
    _push(
        f'Заявка {ticket.number} {decision_text}',
        f'Заявка «{ticket.title}» была {decision_text}.',
        ticket,
        recipients,
    )