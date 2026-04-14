from django.shortcuts import redirect, render
from account.role_permissions import login_required, MenuItem, need_permission, PermissionEnums

from tasks.models import Task
from documents.models import Document

@login_required
def base_redirect(request):
    first_page = MenuItem.first_page(request.user)
    if first_page is not None:
        return redirect(first_page)
    

@need_permission(PermissionEnums.DASHBOARD)
def dashboard(request):
    context = {
        'task_statistic': Task.get_statistic(request),
        'documents': Document.get_available_queryset(request)[:6]
    }

    return render(request, 'site/dashboard/index.html', context)