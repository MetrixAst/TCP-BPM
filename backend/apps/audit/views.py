from datetime import datetime

from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone

from account.role_permissions import RoleEnums, login_required
from project.paginator import CustomPaginator

from .models import AuditLog


def _is_administrator(user):
    return user.is_authenticated and user.role == RoleEnums.ADMINISTRATOR.value


@login_required
def audit_log(request):
    if not _is_administrator(request.user):
        return HttpResponseForbidden('Доступ только для администратора.')

    queryset = AuditLog.objects.select_related('user').order_by('-created_at')

    user_id = request.GET.get('user', '').strip()
    action = request.GET.get('action', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    page = int(request.GET.get('page', 1) or 1)

    if user_id.isdigit():
        queryset = queryset.filter(user_id=int(user_id))
    if action:
        queryset = queryset.filter(action=action)
    if date_from:
        try:
            dt_from = timezone.make_aware(
                datetime.combine(datetime.strptime(date_from, '%Y-%m-%d').date(), datetime.min.time())
            )
            queryset = queryset.filter(created_at__gte=dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = timezone.make_aware(
                datetime.combine(datetime.strptime(date_to, '%Y-%m-%d').date(), datetime.max.time())
            )
            queryset = queryset.filter(created_at__lte=dt_to)
        except ValueError:
            pass

    from account.models import UserAccount
    filter_users = UserAccount.objects.order_by('username')

    context = {
        'logs': CustomPaginator(queryset, page, itemsPerPage=50),
        'actions': AuditLog.Action.choices,
        'filter_users': filter_users,
        'f_user': user_id,
        'f_action': action,
        'f_date_from': date_from,
        'f_date_to': date_to,
    }
    return render(request, 'site/audit/log_list.html', context)
