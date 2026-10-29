"""Отчёт по заявкам за период с группировкой по статусам и выгрузкой в Excel."""

from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Min
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from account.models import Department, UserAccount
from account.role_permissions import PermissionEnums
from account.services.permissions import user_has_permission

from .enums import TicketCategoryEnum, TicketStatusEnum
from .models import ServiceRequest, ServiceRequestHistory

S = TicketStatusEnum

# Группы статусов, которые просит собственник: создано / в работе / исполнено / отклонено.
STATUS_GROUPS = [
    ('created',  'Создано (новые)', [S.NEW.value[0]]),
    ('in_work',  'В работе', [
        S.ACCEPTED.value[0], S.IN_PROGRESS.value[0],
        S.PENDING_APPROVAL.value[0], S.APPROVED.value[0],
    ]),
    ('done',     'Исполнено', [S.DONE.value[0]]),
    ('rejected', 'Отклонено / отменено', [S.REJECTED.value[0], S.CANCELLED.value[0]]),
]
STATUS_TO_GROUP = {status: key for key, _label, statuses in STATUS_GROUPS for status in statuses}


def _check_access(user):
    if not (
        user_has_permission(user, PermissionEnums.REPORTS)
        or user_has_permission(user, PermissionEnums.TICKETS_DISPATCH)
    ):
        raise PermissionDenied('Отчёт по заявкам')


def _filters(request):
    today = timezone.localdate()
    date_from = parse_date(request.GET.get('date_from') or '') or today.replace(day=1)
    date_to = parse_date(request.GET.get('date_to') or '') or today
    return {
        'date_from': date_from,
        'date_to': date_to,
        'department': request.GET.get('department') or '',
        'assignee': request.GET.get('assignee') or '',
        'category': request.GET.get('category') or '',
        'group': request.GET.get('group') or '',
    }


def _queryset(f):
    qs = ServiceRequest.objects.select_related('tenant', 'department', 'assignee', 'author').filter(
        created_at__date__gte=f['date_from'],
        created_at__date__lte=f['date_to'],
    )
    if f['department'] == 'none':
        qs = qs.filter(department__isnull=True)
    elif f['department'].isdigit():
        qs = qs.filter(department_id=int(f['department']))
    if f['assignee'] == 'none':
        qs = qs.filter(assignee__isnull=True)
    elif f['assignee'].isdigit():
        qs = qs.filter(assignee_id=int(f['assignee']))
    if f['category']:
        qs = qs.filter(category=f['category'])
    return qs


def _done_hours(tickets):
    """Часы от создания до первой отметки «Выполнена» по истории заявки."""
    done_at = dict(
        ServiceRequestHistory.objects
        .filter(request__in=tickets, status=S.DONE.value[0])
        .values('request_id')
        .annotate(first=Min('created_at'))
        .values_list('request_id', 'first')
    )
    result = {}
    for ticket in tickets:
        finished = done_at.get(ticket.pk)
        if finished:
            result[ticket.pk] = round((finished - ticket.created_at).total_seconds() / 3600, 1)
    return result


def _build(request):
    _check_access(request.user)
    f = _filters(request)
    base = _queryset(f)

    by_status = dict(base.values_list('status').annotate(cnt=Count('id')))
    groups = []
    for key, label, statuses in STATUS_GROUPS:
        groups.append({
            'key': key,
            'label': label,
            'count': sum(by_status.get(s, 0) for s in statuses),
        })

    rows = base
    if f['group']:
        statuses = next((st for key, _l, st in STATUS_GROUPS if key == f['group']), [])
        rows = rows.filter(status__in=statuses)
    rows = list(rows.order_by('-created_at'))

    hours = _done_hours([t for t in rows if t.status == S.DONE.value[0]])
    for ticket in rows:
        ticket.report_group = STATUS_TO_GROUP.get(ticket.status, '')
        ticket.done_hours = hours.get(ticket.pk)
    done_values = list(hours.values())

    by_department = (
        base.values('department__name')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    return f, {
        'filters': f,
        'groups': groups,
        'total': sum(by_status.values()),
        'rows': rows,
        'avg_done_hours': round(sum(done_values) / len(done_values), 1) if done_values else None,
        'by_department': by_department,
    }


def tickets_report(request):
    _f, context = _build(request)
    context.update({
        'departments': Department.objects.order_by('name'),
        'assignees': UserAccount.objects.filter(
            pk__in=ServiceRequest.objects.exclude(assignee__isnull=True).values('assignee_id'),
        ).order_by('last_name', 'first_name'),
        'categories': TicketCategoryEnum.list(),
        'status_groups': [(key, label) for key, label, _s in STATUS_GROUPS],
    })
    return render(request, 'site/tickets/report.html', context)


def tickets_report_export(request):
    import openpyxl
    from openpyxl.styles import Font

    f, context = _build(request)
    wb = openpyxl.Workbook()

    summary = wb.active
    summary.title = 'Сводка'
    summary.append([f"Отчёт по заявкам за {f['date_from']:%d.%m.%Y} — {f['date_to']:%d.%m.%Y}"])
    summary['A1'].font = Font(bold=True)
    summary.append([])
    summary.append(['Статус', 'Количество'])
    for group in context['groups']:
        summary.append([group['label'], group['count']])
    summary.append(['Всего', context['total']])
    if context['avg_done_hours'] is not None:
        summary.append(['Среднее время исполнения, ч', context['avg_done_hours']])
    summary.append([])
    summary.append(['Подразделение', 'Заявок'])
    for row in context['by_department']:
        summary.append([row['department__name'] or 'Не распределено', row['total']])
    summary.column_dimensions['A'].width = 36

    sheet = wb.create_sheet('Заявки')
    headers = [
        'Номер', 'Создано', 'Тип', 'Тема', 'Арендатор', 'Помещение', 'Подразделение',
        'Исполнитель', 'Статус', 'Приоритет', 'Время исполнения, ч',
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for t in context['rows']:
        sheet.append([
            t.number,
            timezone.localtime(t.created_at).strftime('%d.%m.%Y %H:%M'),
            t.get_category_display(),
            t.title,
            str(t.tenant) if t.tenant else '',
            t.room or '',
            t.department.name if t.department else '',
            t.assignee.get_name if t.assignee else '',
            t.get_status_display(),
            t.get_priority_display(),
            t.done_hours if t.done_hours is not None else '',
        ])
    for col, width in zip('ABCDEFGHIJK', (12, 17, 22, 40, 24, 12, 22, 24, 16, 12, 12)):
        sheet.column_dimensions[col].width = width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f"attachment; filename=tickets_report_{f['date_from']:%Y%m%d}_{f['date_to']:%Y%m%d}.xlsx"
    )
    wb.save(response)
    return response
