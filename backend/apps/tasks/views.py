from django.shortcuts import redirect, render
from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from project.paginator import CustomPaginator
from django.http import Http404, HttpResponseForbidden
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from .enums import TaskStatusEnum
from .models import Task

from .forms import TaskForm


@need_permission(PermissionEnums.TASKS)
def tasks(request):
    return tasks_list(request, 'all')


@need_permission(PermissionEnums.TASKS)
def tasks_list(request, action):
    queryset = Task.get_available_queryset(request)
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))

    if search != '':
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(text__icontains=search)
        )

    if action != 'all':
        queryset = queryset.filter(status=action)

    paginator = CustomPaginator(queryset, page)

    context = {
        'action': action,
        'statuses': TaskStatusEnum.get_full(),
        'paginator': paginator,
        'can_create': RolePermissions.checkPermission(
            request.user.role,
            PermissionEnums.EDIT_TASK
        )
    }

    return render(request, 'site/tasks/tasks.html', context)


@need_permission(PermissionEnums.TASKS)
def task(request, pk):
    current = Task.get_by_id(request, pk)
    current.views = current.views + 1
    current.save(update_fields=['views'])

    context = {
        'task': current,
        'status_info': current.status_info,
        'actions': current.actions(request),
    }

    return render(request, 'site/tasks/task.html', context)


@need_permission(PermissionEnums.TASKS)
def task_action(request, pk, action):
    current = Task.get_by_id(request, pk)

    if action == "cancel":
        current.delete()
        return redirect('tasks:list')

    try:
        current.set_action(request, action)
    except PermissionDenied:
        return HttpResponseForbidden('403 Forbidden')

    return redirect('tasks:task', pk=pk)


@need_permission(PermissionEnums.EDIT_TASK)
def edit_task(request, pk):
    current = Task.get_by_id(request, pk, exception=False)
    if current is not None and current.author != request.user:
        raise Http404

    form = TaskForm(instance=current)

    if request.method == 'POST':
        form = TaskForm(instance=current, data=request.POST)
        if form.is_valid():
            new = form.save(commit=False)
            new.author = request.user
            new.save()
            form.save_m2m()

            if new.status is None or new.status == "":
                new.set_action(request, 'create')

            return redirect('tasks:task', pk=new.pk)

    context = {
        'form': form,
    }

    return render(request, 'site/tasks/edit_task.html', context)