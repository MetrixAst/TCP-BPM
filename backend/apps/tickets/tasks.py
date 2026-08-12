from celery import shared_task
from django.utils import timezone
from datetime import timedelta


@shared_task(name='tickets.sla_escalation')
def sla_escalation():
    from tickets.models import ServiceRequest
    from tickets.enums import TicketStatusEnum
    from tickets.services import get_approver, notify_approval_requested
    from account.models import UserAccount
    from account.role_permissions import RoleEnums

    REMINDER_HOURS = 24  
    ESCALATION_HOURS = 48  

    now = timezone.now()
    pending = ServiceRequest.objects.filter(
        status=TicketStatusEnum.PENDING_APPROVAL.value[0],
        updated_at__lt=now - timedelta(hours=REMINDER_HOURS),
    )

    admin = UserAccount.objects.filter(role=RoleEnums.ADMINISTRATOR.value).first()

    for ticket in pending:
        hours_pending = (now - ticket.updated_at).total_seconds() / 3600

        if hours_pending >= ESCALATION_HOURS:
            if admin:
                notify_approval_requested(ticket, admin)
        else:
            if ticket.author:
                approver = get_approver(ticket.author)
                if approver:
                    notify_approval_requested(ticket, approver)

    return f'Обработано {pending.count()} заявок на согласовании'