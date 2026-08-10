import json

from django.shortcuts import redirect, render
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods

from addits.models import Comment
from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from account.services.access_scope import filter_counterparties_queryset
from onec.models import Counterparty
from project.paginator import CustomPaginator

from .enums import TaskStatusEnum
from .models import Task, TaskFile, TaskChecklistItem, TaskLineItem, TaskUserFlag
from .forms import TaskForm



def is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _can_edit_content(task, user):
    """Кто может править чек-лист / позиции задачи."""
    if getattr(user, 'is_superuser', False):
        return True
    return task._get_user_role(user) in ('author', 'executor', 'co_executor')


def _task_card_dict(task):
    from .enums import TaskTypeEnum, PriorityEnum
    
    # Тип задачи через gettext
    type_display = ''
    for item in TaskTypeEnum:
        if item.value[0] == task.task_type:
            type_display = str(item.value[1])
            break
    
    # Приоритет через gettext
    priority_title = ''
    for item in PriorityEnum:
        if item.value[0] == task.priority:
            priority_title = str(item.value[1])
            break

    return {
        'id': task.id,
        'number': f'#{task.id}',
        'title': task.title,
        'type': type_display,
        'priority': task.priority,
        'priority_title': priority_title,
        'deadline': task.deadline.isoformat() if task.deadline else None,
        'executor': task.executor.get_name if task.executor else None,
        'executor_id': task.executor_id,
        'status': task.status,
        'status_title': task.status_info.get('title', ''),
        'url': reverse('tasks:task', args=[task.id]),
        'status_color': task.status_info.get('color', 'neutral'),
    }


def _kanban_payload(request):
    qs = Task.get_available_queryset(request).select_related('executor', 'author')
    buckets = {}
    for task in qs:
        buckets.setdefault(task.status, []).append(task)
    columns = []
    for slug, title in TaskStatusEnum.list():
        items = [_task_card_dict(t) for t in buckets.get(slug, [])]
        info = TaskStatusEnum.get_info(slug)
        columns.append({
            'status': slug,
            'title': str(title),
            'color': info.get('color', 'neutral'),
            'tasks': items,
        })
    return {'columns': columns}


@need_permission(PermissionEnums.TASKS)
def tasks(request):
    return tasks_list(request, "all")


@need_permission(PermissionEnums.TASKS)
def tasks_list(request, action):
    base_queryset = Task.get_available_queryset(request)
    queryset = base_queryset

    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "").strip()
    page = int(request.GET.get("page", 1))

    if action == "author":
        queryset = queryset.filter(author=request.user)
    elif action == "executor":
        queryset = queryset.filter(
            Q(executor=request.user) | Q(co_executors=request.user)
        ).distinct()
    elif action == "approver":
        queryset = queryset.filter(status="completed")
    elif action == "observer":
        queryset = queryset.filter(observers=request.user)

    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(text__icontains=search)
        )

    if state:
        queryset = queryset.filter(status=state)

    executor_id = request.GET.get('executor', '').strip()
    if executor_id.isdigit():
        queryset = queryset.filter(executor_id=int(executor_id))

    paginator = CustomPaginator(queryset, page)

    context = {
        "action": action,
        "paginator": paginator,
        "role_tabs": {
            "all": {
                "title": "Все",
                "count": base_queryset.count(),
            },
            "author": {
                "title": "Автор",
                "count": base_queryset.filter(author=request.user).count(),
            },
            "executor": {
                "title": "Исполнитель",
                "count": base_queryset.filter(
                    Q(executor=request.user) | Q(co_executors=request.user)
                ).distinct().count(),
            },
            "approver": {
                "title": "Проверка",
                "count": base_queryset.filter(status="completed").count(),
            },
            "observer": {
                "title": "Наблюдатель",
                "count": base_queryset.filter(observers=request.user).count(),
            },
        },
        "can_create": RolePermissions.checkPermission(
            request.user.role,
            PermissionEnums.EDIT_TASK
        ),
    }

    return render(request, "site/tasks/tasks.html", context)


@need_permission(PermissionEnums.TASKS)
def task(request, pk):
    current = Task.get_by_id(request, pk)

    user_role = current._get_user_role(request.user)

    if request.method == "POST" and is_ajax(request):
        changed = []
        if "priority" in request.POST and user_role != "observer":
            current.priority = request.POST.get("priority") or current.priority
            changed.append("priority")
        if "text" in request.POST and user_role in ("author", "executor", "co_executor"):
            current.text = (request.POST.get("text") or "").strip()
            changed.append("text")
        if changed:
            current.save(update_fields=changed)
        return JsonResponse({"ok": True, "text": current.text or ""})

    current.views = current.views + 1
    current.save(update_fields=["views"])

    counterparty_qs = filter_counterparties_queryset(
        Counterparty.objects.all(),
        request.user,
    )

    primary_action = None
    for item in current.actions(request):
        if item.get('action') != 'cancel':
            primary_action = item
            break

    history_items = current.history.select_related("user").all()
    comments = Comment.objects.filter(
        target_type="task", target_id=current.pk
    ).select_related("user")

    updates = []
    for h in history_items:
        updates.append({
            "kind": "status",
            "user": h.user,
            "text": h.title,
            "date": h.date,
        })
    for c in comments:
        updates.append({
            "kind": "comment",
            "user": c.user,
            "text": c.text,
            "date": c.date,
        })
    updates.sort(key=lambda x: x["date"])

    context = {
        "task": current,
        "status_info": current.status_info,
        "actions": current.actions(request),
        "primary_action": primary_action,
        "user_role": user_role,
        "can_edit": user_role == 'author',
        "can_edit_checklist": user_role in ('author', 'executor', 'co_executor'),
        "counterparty_choices": counterparty_qs.order_by('short_name')[:200],
        "comments": comments,
        "updates": updates,
        "checklist_count": current.checklist_items.count(),
        "line_items_count": current.line_items.count(),
        "files_count": current.files.count(),
        "history_count": current.history.count(),
        "is_favorite": current.user_flags.filter(
            user=request.user, flag=TaskUserFlag.FAVORITE
        ).exists(),
    }

    return render(request, "site/tasks/task.html", context)


@need_permission(PermissionEnums.TASKS)
def task_toggle_flag(request, pk):
    """Переключение персональной пометки задачи (избранное) — хранится в БД."""
    current = Task.get_by_id(request, pk)

    if request.method != "POST" or not is_ajax(request):
        return JsonResponse({"ok": False, "message": "Метод не разрешен"}, status=405)

    flag = (request.POST.get("flag") or TaskUserFlag.FAVORITE).strip()
    valid_flags = {choice[0] for choice in TaskUserFlag.FLAG_CHOICES}
    if flag not in valid_flags:
        return JsonResponse({"ok": False, "message": "Неизвестный флаг"}, status=400)

    desired = request.POST.get("state")
    obj = TaskUserFlag.objects.filter(
        user=request.user, task=current, flag=flag
    ).first()

    if desired is None:
        active = obj is None
    else:
        active = desired in ("1", "true", "True", "on")

    if active and obj is None:
        TaskUserFlag.objects.create(user=request.user, task=current, flag=flag)
    elif not active and obj is not None:
        obj.delete()

    return JsonResponse({"ok": True, "flag": flag, "active": active})


@need_permission(PermissionEnums.TASKS)
def task_action(request, pk, action):
    current = Task.get_by_id(request, pk)

    if request.method != "POST":
        if is_ajax(request):
            return JsonResponse({"ok": False, "message": "Метод не разрешен"}, status=405)
        return HttpResponseForbidden("405 Method Not Allowed")

    if action == "cancel":
        if not current.can_delete(request.user):
            if is_ajax(request):
                return JsonResponse({"ok": False, "message": "Нет прав на удаление"}, status=403)
            return HttpResponseForbidden("403 Forbidden")
        reason = request.POST.get('reason', '').strip()
        if len(reason) < 5:
            if is_ajax(request):
                return JsonResponse({"ok": False, "message": "Причина должна содержать не менее 5 символов"}, status=400)
            return HttpResponseForbidden("Причина слишком короткая")
        current.soft_delete(request.user, reason=reason)
        if is_ajax(request):
            return JsonResponse({
                "ok": True,
                "redirect": "/tasks/",
                "message": "Задача удалена"
            })
        return redirect("tasks:list")

    try:
        current.set_action(request, action)
    except PermissionDenied as e:
        if is_ajax(request):
            return JsonResponse({"ok": False, "message": str(e)}, status=403)
        return HttpResponseForbidden("403 Forbidden")

    current.refresh_from_db()

    if is_ajax(request):
        return JsonResponse({
            "ok": True,
            "task_id": current.id,
            "status": current.status,
            "status_title": current.status_info.get("title"),
            "status_color": current.status_info.get("color"),
            "message": "Действие выполнено",
        })

    return redirect("tasks:task", pk=pk)


@need_permission(PermissionEnums.EDIT_TASK)
def edit_task(request, pk):
    current = Task.get_by_id(request, pk, exception=False)

    if current is not None and current.author != request.user:
        raise Http404

    form = TaskForm(instance=current, user=request.user)

    if request.method == "POST":
        form = TaskForm(instance=current, data=request.POST, user=request.user)

        if form.is_valid():
            new = form.save(commit=False)
            new.author = request.user
            new.save()
            form.save_m2m()

            for uploaded_file in request.FILES.getlist("attachments"):
                TaskFile.objects.create(
                    task=new,
                    file=uploaded_file,
                    uploaded_by=request.user
                )

            if not new.status:
                new.set_action(request, "create")

            if is_ajax(request):
                return JsonResponse({
                    "ok": True,
                    "redirect": f"/tasks/task/{new.pk}",
                    "message": "Задача сохранена"
                })

            return redirect("tasks:task", pk=new.pk)

        if is_ajax(request):
            return JsonResponse({
                "ok": False,
                "errors": form.errors,
                "message": "Проверьте поля формы"
            }, status=400)

    counterparty_qs = filter_counterparties_queryset(
        Counterparty.objects.all(),
        request.user,
    )

    context = {
        "form": form,
        "task": current,
        "counterparty_choices": counterparty_qs.order_by('short_name')[:200],
    }

    return render(request, "site/tasks/edit_task.html", context)


@need_permission(PermissionEnums.TASKS)
def kanban(request):
    context = {
        'view_mode': 'kanban',
        'can_create': RolePermissions.checkPermission(
            request.user.role,
            PermissionEnums.EDIT_TASK,
        ),
    }
    return render(request, 'site/tasks/kanban.html', context)


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['GET'])
def kanban_api(request):
    return JsonResponse(_kanban_payload(request))


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['PATCH', 'POST'])
def kanban_status(request, pk):
    if request.content_type and 'application/json' in request.content_type:
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = request.POST

    new_status = payload.get('status')
    if not new_status:
        return JsonResponse({'ok': False, 'message': 'Укажите status'}, status=400)

    task = Task.get_by_id(request, pk)
    try:
        task.transition_to_status(request, new_status)
    except PermissionDenied as exc:
        return JsonResponse({'ok': False, 'message': str(exc)}, status=403)

    task.refresh_from_db()
    try:
        kanban = _kanban_payload(request)
    except Exception as exc:
        return JsonResponse({
            'ok': True,
            'task': _task_card_dict(task),
            'kanban': None,
            'warning': str(exc),
        })

    return JsonResponse({
        'ok': True,
        'task': _task_card_dict(task),
        'kanban': kanban,
    })


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['POST'])
def checklist_add(request, pk):
    task = Task.get_by_id(request, pk)
    if not _can_edit_content(task, request.user):
        return JsonResponse({'ok': False, 'message': 'Недостаточно прав'}, status=403)
    title = (request.POST.get('title') or '').strip()
    if not title:
        return JsonResponse({'ok': False, 'message': 'Пустой пункт'}, status=400)

    item = TaskChecklistItem.objects.create(
        task=task,
        title=title,
        sort_order=task.checklist_items.count(),
    )
    return JsonResponse({
        'ok': True,
        'item': {'id': item.id, 'title': item.title, 'is_done': item.is_done},
    })


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['POST'])
def checklist_toggle(request, pk, item_id):
    task = Task.get_by_id(request, pk)
    if not _can_edit_content(task, request.user):
        return JsonResponse({'ok': False, 'message': 'Недостаточно прав'}, status=403)
    item = task.checklist_items.filter(pk=item_id).first()
    if not item:
        raise Http404
    item.is_done = not item.is_done
    item.save(update_fields=['is_done'])
    return JsonResponse({'ok': True, 'is_done': item.is_done})


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['POST'])
def line_item_add(request, pk):
    task = Task.get_by_id(request, pk)
    if not _can_edit_content(task, request.user):
        return JsonResponse({'ok': False, 'message': 'Недостаточно прав'}, status=403)

    from .forms import TaskLineItemForm
    form = TaskLineItemForm(request.POST)
    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0]
        return JsonResponse({'ok': False, 'message': first_error, 'errors': form.errors}, status=400)

    item = TaskLineItem.objects.create(
        task=task,
        name=form.cleaned_data['name'],
        quantity=form.cleaned_data['quantity'],
        price=form.cleaned_data['price'],
        unit=form.cleaned_data['unit'],
    )

    all_items = task.line_items.all()
    grand_total = sum(i.total for i in all_items)

    return JsonResponse({
        'ok': True,
        'item': {
            'id': item.id,
            'name': item.name,
            'quantity': str(item.quantity),
            'unit': item.unit,
            'price': str(item.price),
            'total': str(item.total),
        },
        'grand_total': str(grand_total),
        'items_count': all_items.count(),
    })


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['POST'])
def task_file_add(request, pk):
    task = Task.get_by_id(request, pk)
    uploaded = request.FILES.getlist('files') or request.FILES.getlist('file')
    if not uploaded:
        return JsonResponse({'ok': False, 'message': 'Файл не выбран'}, status=400)

    created = []
    for f in uploaded:
        obj = TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)
        created.append({
            'id': obj.id,
            'name': obj.filename,
            'url': obj.file.url,
            'size': obj.file.size,
            'uploaded_by': request.user.get_name,
            'oo_url': request.build_absolute_uri(f'/doc/attachment/task_file/{obj.id}/editor/') if obj.filename.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')) else None,
        })
    return JsonResponse({'ok': True, 'files': created})


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['POST'])
def task_file_delete(request, pk, file_id):
    task = Task.get_by_id(request, pk)
    f = task.files.filter(pk=file_id).first()
    if not f:
        raise Http404
    if task._get_user_role(request.user) == 'observer':
        return JsonResponse({'ok': False, 'message': 'Нет доступа'}, status=403)
    f.delete()
    return JsonResponse({'ok': True})


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['POST'])
def task_counterparty(request, pk):
    task = Task.get_by_id(request, pk)
    cp_id = request.POST.get('counterparty_id')
    if not cp_id:
        task.counterparty = None
        task.save(update_fields=['counterparty'])
        return JsonResponse({'ok': True, 'counterparty': None})

    cp = filter_counterparties_queryset(
        Counterparty.objects.filter(pk=cp_id),
        request.user,
    ).first()
    if not cp:
        return JsonResponse({'ok': False, 'message': 'Нет доступа к контрагенту'}, status=403)

    task.counterparty = cp
    task.save(update_fields=['counterparty'])
    return JsonResponse({'ok': True, 'counterparty': {'id': cp.id, 'name': str(cp)}})