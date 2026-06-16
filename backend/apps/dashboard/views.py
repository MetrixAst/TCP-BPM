from django.shortcuts import redirect, render
from account.role_permissions import login_required, MenuItem, need_permission, PermissionEnums

from tasks.models import Task
from documents.models import Document

@login_required
def base_redirect(request):
    first_page = MenuItem.first_page(request.user)
    if first_page is not None:
        return redirect(first_page)
    return redirect('dashboard:dashboard')

@need_permission(PermissionEnums.DASHBOARD)
def dashboard(request):
    from datetime import date

    new_tasks = Task.get_available_queryset(request).filter(
        status='created'
    ).select_related('author', 'executor').order_by('-id')[:5]

    today_checkin_status = None
    employee = getattr(request.user, 'employee_info', None)
    if employee:
        try:
            from hr.models import AttendanceRecord, CheckInEnum
            today = date.today()
            summary = AttendanceRecord.get_daily_summary(employee, today)
            events = summary.get('details', {})
            if CheckInEnum.DAY_END in events:
                today_checkin_status = 'completed'
            elif CheckInEnum.DAY_START in events:
                today_checkin_status = 'checked_in'
            else:
                today_checkin_status = 'not_checked_in'
        except Exception:
            today_checkin_status = None

    context = {
        'task_statistic': Task.get_statistic(request),
        'new_tasks': new_tasks,
        'today_checkin_status': today_checkin_status,
    }
    return render(request, 'site/dashboard/index.html', context)