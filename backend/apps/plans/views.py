from datetime import date, datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from account.models import Department
from account.role_permissions import login_required
from .access import (
    can_edit_plan, can_update_item, can_view_all, can_view_plan, creatable_departments,
    has_plans_access, is_plans_admin, managed_department_ids, own_department_id,
)
from .forms import PlanItemForm, PlanItemProgressForm
from .models import DepartmentPlan, PlanItem, month_start


def _month_from_request(request):
    raw = request.GET.get('month') or request.POST.get('month') or ''
    try:
        return datetime.strptime(raw, '%Y-%m').date()
    except ValueError:
        return month_start()


def _shift_month(value, delta):
    index = value.year * 12 + value.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def _visible_plans(user, month):
    plans = DepartmentPlan.objects.filter(month=month).select_related('department', 'author')
    if can_view_all(user) or is_plans_admin(user):
        return plans
    from django.db.models import Q

    dept_ids = set(managed_department_ids(user))
    if own_department_id(user):
        dept_ids.add(own_department_id(user))
    return plans.filter(Q(department_id__in=dept_ids) | Q(items__responsible=user)).distinct()


def _get_plan(request, pk):
    plan = get_object_or_404(DepartmentPlan.objects.select_related('department', 'author'), pk=pk)
    if not can_view_plan(request.user, plan):
        raise PermissionDenied('План отдела')
    return plan


def _sync_items(items):
    for item in items:
        if item.task_id:
            item.sync_from_task()


@login_required
def plans_list(request):
    if not has_plans_access(request.user):
        raise PermissionDenied('Планы отделов')

    month = _month_from_request(request)
    plans = list(_visible_plans(request.user, month).prefetch_related('items__task'))
    rows = []
    for plan in plans:
        items = list(plan.items.all())
        _sync_items(items)
        rows.append({'plan': plan, 'stats': plan.stats(items), 'can_edit': can_edit_plan(request.user, plan)})

    totals = {key: sum(r['stats'][key] for r in rows) for key in ('total', 'done', 'in_progress', 'overdue')}
    totals['progress'] = round(totals['done'] / totals['total'] * 100) if totals['total'] else 0

    planned_dept_ids = {plan.department_id for plan in plans}
    creatable = [d for d in creatable_departments(request.user) if d.pk not in planned_dept_ids]
    missing = []
    if can_view_all(request.user) or is_plans_admin(request.user):
        missing = list(
            Department.objects.filter(level_type='department')
            .exclude(pk__in=planned_dept_ids).order_by('name')
        )

    my_items = (
        PlanItem.objects.filter(responsible=request.user, plan__month=month)
        .exclude(status=PlanItem.STATUS_CANCELLED)
        .select_related('plan__department')
    )

    return render(request, 'site/plans/plans_list.html', {
        'month': month,
        'prev_month': _shift_month(month, -1),
        'next_month': _shift_month(month, 1),
        'rows': rows,
        'totals': totals,
        'creatable': creatable,
        'missing': missing,
        'my_items': my_items,
        'can_view_all': can_view_all(request.user),
    })


@login_required
@require_POST
def plan_create(request):
    month = _month_from_request(request)
    department = get_object_or_404(Department, pk=request.POST.get('department'))
    if department not in creatable_departments(request.user):
        raise PermissionDenied('Создание плана')

    plan, created = DepartmentPlan.objects.get_or_create(
        department=department, month=month, defaults={'author': request.user},
    )
    if created and request.POST.get('carry_over'):
        previous = DepartmentPlan.objects.filter(department=department, month=_shift_month(month, -1)).first()
        if previous:
            carried = previous.items.filter(status__in=PlanItem.OPEN_STATUSES)
            for item in carried:
                PlanItem.objects.create(
                    plan=plan, title=item.title, description=item.description,
                    responsible=item.responsible, deadline=max(item.deadline, month),
                    status=item.status, result=item.result, task=item.task, order=item.order,
                )
            if carried:
                messages.info(request, f'Перенесено незавершённых пунктов: {len(carried)}.')
    return redirect('plans:detail', pk=plan.pk)


@login_required
def plan_detail(request, pk):
    plan = _get_plan(request, pk)
    items = list(plan.items.select_related('responsible', 'task'))
    _sync_items(items)
    editable = can_edit_plan(request.user, plan)
    for item in items:
        item.can_update = editable or item.responsible_id == request.user.id

    form = PlanItemForm(plan=plan) if editable else None

    return render(request, 'site/plans/plan_detail.html', {
        'plan': plan,
        'items': items,
        'stats': plan.stats(items),
        'can_edit': editable,
        'form': form,
        'status_choices': PlanItem.STATUS_CHOICES,
    })


@login_required
@require_POST
def plan_update_note(request, pk):
    plan = _get_plan(request, pk)
    if not can_edit_plan(request.user, plan):
        raise PermissionDenied('Редактирование плана')
    plan.note = (request.POST.get('note') or '').strip()
    plan.save(update_fields=['note', 'updated_at'])
    return redirect('plans:detail', pk=plan.pk)


@login_required
@require_POST
def plan_delete(request, pk):
    plan = _get_plan(request, pk)
    if not can_edit_plan(request.user, plan):
        raise PermissionDenied('Удаление плана')
    month = plan.month
    plan.delete()
    messages.success(request, 'План удалён.')
    return redirect(f"{_list_url()}?month={month:%Y-%m}")


def _list_url():
    from django.urls import reverse
    return reverse('plans:list')


@login_required
@require_POST
def item_create(request, pk):
    plan = _get_plan(request, pk)
    if not can_edit_plan(request.user, plan):
        raise PermissionDenied('Редактирование плана')
    form = PlanItemForm(request.POST, plan=plan)
    if form.is_valid():
        item = form.save(commit=False)
        item.plan = plan
        item.order = plan.items.count()
        item.set_status(item.status)
        item.save()
        messages.success(request, 'Пункт добавлен.')
    else:
        errors = '; '.join(f'{form.fields[f].label}: {e[0]}' for f, e in form.errors.items() if f in form.fields)
        messages.error(request, f'Пункт не добавлен. {errors}')
    return redirect('plans:detail', pk=plan.pk)


@login_required
def item_edit(request, pk):
    item = get_object_or_404(PlanItem.objects.select_related('plan__department'), pk=pk)
    plan = item.plan
    if not can_update_item(request.user, item):
        raise PermissionDenied('Пункт плана')

    full = can_edit_plan(request.user, plan)
    form_class = PlanItemForm if full else PlanItemProgressForm
    kwargs = {'plan': plan} if full else {}
    form = form_class(request.POST or None, instance=item, **kwargs)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        updated.set_status(updated.status)
        updated.save()
        messages.success(request, 'Пункт сохранён.')
        return redirect('plans:detail', pk=plan.pk)

    return render(request, 'site/plans/item_form.html', {'item': item, 'plan': plan, 'form': form, 'full': full})


@login_required
@require_POST
def item_status(request, pk):
    item = get_object_or_404(PlanItem.objects.select_related('plan'), pk=pk)
    if not can_update_item(request.user, item):
        raise PermissionDenied('Пункт плана')
    status = request.POST.get('status')
    if status in dict(PlanItem.STATUS_CHOICES):
        item.set_status(status)
        item.save(update_fields=['status', 'completed_at', 'updated_at'])
    return redirect('plans:detail', pk=item.plan_id)


@login_required
@require_POST
def item_delete(request, pk):
    item = get_object_or_404(PlanItem.objects.select_related('plan'), pk=pk)
    if not can_edit_plan(request.user, item.plan):
        raise PermissionDenied('Пункт плана')
    plan_id = item.plan_id
    item.delete()
    messages.success(request, 'Пункт удалён.')
    return redirect('plans:detail', pk=plan_id)


@login_required
@require_POST
def item_create_task(request, pk):
    """Создаёт задачу в «Менеджере задач» по пункту плана и связывает их."""
    from tasks.models import Task

    item = get_object_or_404(PlanItem.objects.select_related('plan__department', 'responsible'), pk=pk)
    if not can_edit_plan(request.user, item.plan):
        raise PermissionDenied('Пункт плана')
    if item.task_id:
        return redirect('tasks:task', pk=item.task_id)
    if not item.responsible_id:
        messages.error(request, 'Назначьте ответственного, чтобы создать задачу.')
        return redirect('plans:detail', pk=item.plan_id)

    with transaction.atomic():
        task = Task(
            author=request.user,
            executor=item.responsible,
            deadline=item.deadline,
            title=item.title[:120],
            text=(
                f'Пункт плана «{item.plan.department.name}» на {item.plan.month:%m.%Y}.\n\n{item.description}'
            ).strip()[:2000],
        )
        task.set_action(request, 'create')
        item.task = task
        if item.status == PlanItem.STATUS_PLANNED:
            item.set_status(PlanItem.STATUS_IN_PROGRESS)
        item.save(update_fields=['task', 'status', 'completed_at', 'updated_at'])

    messages.success(request, f'Задача создана и назначена: {item.responsible.get_name}.')
    return redirect('plans:detail', pk=item.plan_id)


@login_required
def plans_export(request):
    import openpyxl
    from django.utils import timezone
    from openpyxl.styles import Font

    if not has_plans_access(request.user):
        raise PermissionDenied('Планы отделов')
    month = _month_from_request(request)
    plans = list(_visible_plans(request.user, month).prefetch_related('items__responsible', 'items__task'))

    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = 'Сводка'
    summary.append([f'Планы отделов на {month:%m.%Y}'])
    summary['A1'].font = Font(bold=True)
    summary.append([])
    summary.append(['Отдел', 'Пунктов', 'Выполнено', 'В работе', 'Просрочено', 'Выполнение, %'])
    detail = wb.create_sheet('Пункты')
    detail.append(['Отдел', 'Работа / задача', 'Ответственный', 'Срок', 'Статус', 'Просрочено', 'Результат', 'Выполнено'])
    for row in (summary[3], detail[1]):
        for cell in row:
            cell.font = Font(bold=True)

    for plan in plans:
        items = list(plan.items.all())
        _sync_items(items)
        stats = plan.stats(items)
        summary.append([
            plan.department.name, stats['total'], stats['done'], stats['in_progress'],
            stats['overdue'], stats['progress'],
        ])
        for item in items:
            detail.append([
                plan.department.name,
                item.title,
                item.responsible.get_name if item.responsible else '',
                item.deadline.strftime('%d.%m.%Y'),
                item.get_status_display(),
                'да' if item.is_overdue else '',
                item.result,
                timezone.localtime(item.completed_at).strftime('%d.%m.%Y') if item.completed_at else '',
            ])

    summary.column_dimensions['A'].width = 32
    for col, width in zip('ABCDEFGH', (28, 46, 26, 12, 14, 12, 46, 12)):
        detail.column_dimensions[col].width = width

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=plans_{month:%Y_%m}.xlsx'
    wb.save(response)
    return response
