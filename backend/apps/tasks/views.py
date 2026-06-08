import json
from django.shortcuts import redirect, render, get_object_or_404
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods

from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from project.paginator import CustomPaginator

from .enums import TaskStatusEnum
from .models import Task, TaskFile
from .forms import TaskForm


def is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


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

    paginator = CustomPaginator(queryset, page)

    context = {
        "action": action,
        "paginator": paginator,
        "role_tabs": {
            "all": {"title": "Все", "count": base_queryset.count()},
            "author": {"title": "Автор", "count": base_queryset.filter(author=request.user).count()},
            "executor": {
                "title": "Исполнитель",
                "count": base_queryset.filter(
                    Q(executor=request.user) | Q(co_executors=request.user)
                ).distinct().count(),
            },
            "approver": {"title": "Проверка", "count": base_queryset.filter(status="completed").count()},
            "observer": {"title": "Наблюдатель", "count": base_queryset.filter(observers=request.user).count()},
        },
        "can_create": RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_TASK),
    }

    return render(request, "site/tasks/tasks.html", context)


@need_permission(PermissionEnums.TASKS)
def task(request, pk):
    current = Task.get_by_id(request, pk)
    current.views = current.views + 1
    current.save(update_fields=["views"])
    user_role = current._get_user_role(request.user)
    context = {
        "task": current,
        "status_info": current.status_info,
        "actions": current.actions(request),
        "user_role": user_role,
    }
    return render(request, "site/tasks/task.html", context)


@need_permission(PermissionEnums.TASKS)
def task_action(request, pk, action):
    current = Task.get_by_id(request, pk)

    if request.method != "POST" and is_ajax(request):
        return JsonResponse({"ok": False, "message": "Метод не разрешен"}, status=405)

    if action == "cancel":
        current.delete()
        if is_ajax(request):
            return JsonResponse({"ok": True, "redirect": "/tasks/", "message": "Задача удалена"})
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

    form = TaskForm(instance=current)

    if request.method == "POST":
        form = TaskForm(instance=current, data=request.POST)

        if form.is_valid():
            new = form.save(commit=False)
            new.author = request.user
            new.save()
            form.save_m2m()

            for uploaded_file in request.FILES.getlist("attachments"):
                TaskFile.objects.create(task=new, file=uploaded_file, uploaded_by=request.user)

            if not new.status:
                new.set_action(request, "create")

            if is_ajax(request):
                return JsonResponse({"ok": True, "redirect": f"/tasks/task/{new.pk}", "message": "Задача сохранена"})

            return redirect("tasks:task", pk=new.pk)

        if is_ajax(request):
            return JsonResponse({"ok": False, "errors": form.errors, "message": "Проверьте поля формы"}, status=400)

    context = {"form": form, "task": current}
    return render(request, "site/tasks/edit_task.html", context)


@need_permission(PermissionEnums.TASKS)
def kanban(request):
    context = {
        "can_create": RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_TASK),
    }
    return render(request, "site/tasks/kanban.html", context)


@need_permission(PermissionEnums.TASKS)
def kanban_board(request):
    queryset = Task.get_available_queryset(request)
    statuses = TaskStatusEnum.list()

    sort = request.GET.get('sort', '-id')
    allowed_sorts = ['-id', 'deadline', '-deadline', 'priority']
    if sort not in allowed_sorts:
        sort = '-id'

    limit = int(request.GET.get('limit', 20))
    offset = int(request.GET.get('offset', 0))

    board = []
    for status_slug, status_title in statuses:
        tasks_qs = queryset.filter(status=status_slug).select_related('author', 'executor').order_by(sort)
        total = tasks_qs.count()
        tasks_page = tasks_qs[offset:offset + limit]

        board.append({
            'status': status_slug,
            'title': status_title,
            'count': total,
            'has_more': total > offset + limit,
            'tasks': [
                {
                    'id': t.id,
                    'title': t.title,
                    'priority': t.priority,
                    'deadline': str(t.deadline) if t.deadline else None,
                    'author': t.author.get_name if t.author else None,
                    'executor': t.executor.get_name if t.executor else None,
                    'task_type': t.task_type,
                    'available_actions': [a['action'] for a in t.actions(request)],
                }
                for t in tasks_page
            ],
        })

    return JsonResponse({'board': board})


@need_permission(PermissionEnums.TASKS)
@require_http_methods(['PATCH'])
def kanban_patch_status(request, pk):
    task = Task.get_by_id(request, pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    if not action:
        return JsonResponse({'error': 'action is required'}, status=400)

    from account.role_permissions import RoleEnums
    role = request.user.role.value if hasattr(request.user.role, 'value') else request.user.role
    is_admin = role in (RoleEnums.ADMINISTRATOR.value, RoleEnums.OWNER.value)

    try:
        if not is_admin:
            task._check_action_permission(request.user, action)
        task.set_action(request, action)
    except PermissionDenied as e:
        return JsonResponse({'error': str(e)}, status=403)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'id': task.id, 'status': task.status, 'status_title': task.status_info.get('title', '')})


@need_permission(PermissionEnums.TASKS)
def checklist_create(request, task_pk):
    task = Task.get_by_id(request, task_pk)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'text is required'}, status=400)

    from .models import TaskChecklist
    item = TaskChecklist.objects.create(
        task=task, text=text, created_by=request.user, order=data.get('order', 0),
    )
    return JsonResponse({'id': item.id, 'text': item.text, 'is_done': item.is_done})


@need_permission(PermissionEnums.TASKS)
def checklist_update(request, task_pk, item_pk):
    Task.get_by_id(request, task_pk)

    if request.method != 'PATCH':
        return JsonResponse({'error': 'PATCH only'}, status=405)

    from .models import TaskChecklist
    item = get_object_or_404(TaskChecklist, pk=item_pk, task_id=task_pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if 'is_done' in data:
        item.is_done = data['is_done']
    if 'text' in data:
        item.text = data['text']
    item.save()

    return JsonResponse({'id': item.id, 'text': item.text, 'is_done': item.is_done})


@need_permission(PermissionEnums.TASKS)
def checklist_delete(request, task_pk, item_pk):
    Task.get_by_id(request, task_pk)

    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE only'}, status=405)

    from .models import TaskChecklist
    item = get_object_or_404(TaskChecklist, pk=item_pk, task_id=task_pk)
    item.delete()

    return JsonResponse({'success': True})


@need_permission(PermissionEnums.TASKS)
def line_items_list(request, task_pk):
    task = Task.get_by_id(request, task_pk)
    from .models import TaskLineItem
    items = task.line_items.all()
    return JsonResponse({
        'items': [
            {'id': i.id, 'name': i.name, 'quantity': str(i.quantity), 'unit': i.unit, 'price': str(i.price), 'total': str(i.total)}
            for i in items
        ]
    })


@need_permission(PermissionEnums.TASKS)
def line_item_create(request, task_pk):
    task = Task.get_by_id(request, task_pk)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)

    from .models import TaskLineItem
    item = TaskLineItem.objects.create(
        task=task, name=name,
        quantity=data.get('quantity', 1),
        unit=data.get('unit', ''),
        price=data.get('price', 0),
    )
    return JsonResponse({
        'id': item.id, 'name': item.name, 'quantity': str(item.quantity),
        'unit': item.unit, 'price': str(item.price), 'total': str(item.total),
    })


@need_permission(PermissionEnums.TASKS)
def line_item_delete(request, task_pk, item_pk):
    Task.get_by_id(request, task_pk)

    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE only'}, status=405)

    from .models import TaskLineItem
    item = get_object_or_404(TaskLineItem, pk=item_pk, task_id=task_pk)
    item.delete()

    return JsonResponse({'success': True})