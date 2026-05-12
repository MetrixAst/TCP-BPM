import openpyxl
import json
import base64
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.db import transaction
from django.utils.dateparse import parse_date
from datetime import datetime, date, timedelta, time


from project.utils import get_or_none, get_or_error
from project.paginator import CustomPaginator

from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from account.models import Employee, Department
from account.forms import EmployeeForm

from .forms import (
    CalendarItemForm, EmployeeCreationForm, EmployeesListForm, 
    LeaveFilterForm, LeaveRequestForm
)
from .models import (
    CalendarItem, Company, Position, LeaveRequest, 
    LeaveType, Vacation, SickLeave, EmploymentContract, AttendanceRecord, CheckInEnum
)
from .serializers import CalendarItemSerializer
from .enums import CalendarItemType, LeaveStatusEnum

import calendar as calendar_module


@need_permission(PermissionEnums.HR)
def structure(request):
    return render(request, 'site/hr/org.html')


@need_permission(PermissionEnums.HR)
def employees(request):

    page = 1
    queryset = Employee.objects.all()
    ordered = False
    form = EmployeesListForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        filters = form.cleaned_data

        page = filters.get('page', 1)

        search = filters.get('search', '')
        if search != '':
            queryset = queryset.filter(Q(user__first_name__icontains=search) | Q(user__username__icontains=search))

        department = filters.get('department', None)
        if department is not None:
            queryset = queryset.filter(department=department)

        position = filters.get('position', None)
        if position is not None:
            queryset = queryset.filter(position=position)

        status = filters.get('status', '')
        if status != '':
            queryset = queryset.filter(status=status)

        ordering = filters.get('ordering', '')
        if ordering != '':
            if ordering == 'name':
                queryset = queryset.order_by('user__first_name')
                ordered = True
            elif ordering == 'department':
                queryset = queryset.order_by('department__name')
                ordered = True
            elif ordering == 'id':
                queryset = queryset.order_by('-id')
                ordered = True

    if not ordered:
        queryset = queryset.order_by('user__username')

    paginator = CustomPaginator(queryset, page)

    context = {
        'form': form,
        'paginator': paginator,
    }

    return render(request, 'site/hr/employees.html', context)


@need_permission(PermissionEnums.HR)
@transaction.atomic
def create_employee(request):

    form = EmployeeCreationForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = form['user'].save()
            employee = form['employee'].save(commit=False)
            employee.user = user
            employee.save()

            if employee.head:
                employee.set_head()

            return redirect('hr:employees')

    context = {
        'form': form,
    }

    return render(request, 'site/hr/create_employee.html', context)


@need_permission(PermissionEnums.HR)
def edit_employee(request, pk):

    employee = get_object_or_404(Employee, pk=pk)

    form = EmployeeForm(request.POST or None, instance=employee)

    if request.method == 'POST':
        if form.is_valid():

            employee = form.save()
            if employee.head:
                employee.set_head()

            return redirect('hr:employees')

    context = {
        'form': form,
        'employee': employee,
    }

    return render(request, 'site/hr/edit_employee.html', context)


@need_permission(PermissionEnums.HR)
def calendar(request, category):

    context = {
        'category': category,
        'category_title': CalendarItemType.get_title(category)
    }

    return render(request, 'site/hr/calendar.html', context)


@need_permission(PermissionEnums.HR)
def calendar_json(request, category):
    qs = CalendarItem.objects.filter(category=category)
    res = CalendarItemSerializer(qs, many=True)

    return JsonResponse(res.data, safe=False)


@need_permission(PermissionEnums.HR)
def edit_calendar_item(request, pk):
    current = get_or_none(CalendarItem, id=pk)
    form = CalendarItemForm(data=request.POST or None, instance=current)

    if request.method == 'POST':
        if form.is_valid():
            new = form.save()
            return redirect('hr:calendar', category=new.category)

    context = {
        'form': form,
    }

    return render(request, 'site/hr/edit_calendar.html', context)


@need_permission(PermissionEnums.HR)
def delete_calendar_item(request, pk):
    current = get_or_none(CalendarItem, id=pk)
    category = current.category

    current.delete()

    return redirect('hr:calendar', category=category)


@need_permission(PermissionEnums.HR)
def companies(request):
    queryset = Company.objects.all().order_by('name')
    for company in queryset:
        company.employee_count = company.get_employees_count()
    
    context = {
        'companies': queryset,
    }
    return render(request, 'site/hr/companies.html', context)

@need_permission(PermissionEnums.HR)
def positions(request):
    queryset = Position.objects.all().order_by('department__name', 'title')
    context = {
        'positions': queryset,
    }
    return render(request, 'site/hr/positions.html', context)


def _is_manager(user):
    employee = getattr(user, 'employee_info', None)
    if employee and employee.head:
        return True
        
    role = user.role
    if hasattr(role, 'value'):
        role = role.value
        
    if RolePermissions.checkPermission(role, PermissionEnums.HR):
        return True
        
    return False

@login_required
def leave_list(request):
    queryset = LeaveRequest.objects.all().select_related(
        'employee__user',
        'employee__department',
        'leave_type',
        'approver__user',
    ).order_by('-id')

    filter_form = LeaveFilterForm(request.GET)

    if filter_form.is_valid():
        data = filter_form.cleaned_data

        search = data.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(employee__user__first_name__icontains=search) |
                Q(employee__user__last_name__icontains=search)
            )

        if data.get('department'):
            queryset = queryset.filter(employee__department=data['department'])

        if data.get('status'):
            queryset = queryset.filter(status=data['status'])

        if data.get('leave_type'):
            queryset = queryset.filter(leave_type=data['leave_type'])

        if data.get('date_from'):
            queryset = queryset.filter(start_date__gte=data['date_from'])

        if data.get('date_to'):
            queryset = queryset.filter(end_date__lte=data['date_to'])

    context = {
        'leaves': queryset,
        'filter_form': filter_form,
        'is_manager': _is_manager(request.user),
    }

    return render(request, 'site/hr/leave_list.html', context)

@login_required
def leave_create(request):
    employee = getattr(request.user, 'employee_info', None)

    if not employee:
        messages.error(request, "Профиль сотрудника не найден.")
        return redirect('hr:leave_list')

    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            leave.status = LeaveStatusEnum.PENDING
            leave.save()
            messages.success(request, "Заявка успешно отправлена.")
            return redirect('hr:leave_list')
    else:
        form = LeaveRequestForm()

    context = {
        'form': form,
    }

    return render(request, 'site/hr/leave_create.html', context)

@login_required
def leave_detail(request, pk):
    leave = get_object_or_404(
        LeaveRequest.objects.select_related(
            'employee__user',
            'employee__department',
            'leave_type',
            'approver__user',
        ),
        pk=pk
    )

    is_owner = (leave.employee == getattr(request.user, 'employee_info', None))
    if not is_owner and not _is_manager(request.user):
        messages.error(request, "Нет доступа.")
        return redirect('hr:leave_list')

    context = {
        'leave': leave,
        'is_manager': _is_manager(request.user),
        'is_owner': is_owner,
    }
    return render(request, 'site/hr/leave_detail.html', context)


@login_required
def leave_approve(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    
    if request.method == 'POST':
        if _is_manager(request.user) and leave.status == LeaveStatusEnum.PENDING:
            leave.status = LeaveStatusEnum.APPROVED
            leave.approver = request.user.employee_info
            leave.save()
            messages.success(request, "Заявка одобрена.")
    
    return redirect('hr:leave_list')


@login_required
def leave_reject(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    
    if request.method == 'POST':
        if _is_manager(request.user) and leave.status == LeaveStatusEnum.PENDING:
            leave.status = LeaveStatusEnum.REJECTED
            leave.save()
            messages.warning(request, "Заявка отклонена.")
            
    return redirect('hr:leave_list')

@login_required
def leave_cancel(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk, employee__user=request.user)

    if request.method == 'POST':
        if leave.status in [LeaveStatusEnum.DRAFT, LeaveStatusEnum.PENDING]:
            leave.delete()
            messages.success(request, "Заявка успешно удалена.")
    
    return redirect('hr:leave_list')

@login_required
def ajax_calculate_days(request):
    start = request.GET.get('start')
    end = request.GET.get('end')

    if not start or not end:
        return JsonResponse({'days': 0})

    try:
        employee = getattr(request.user, 'employee_info', None)
        if not employee:
            return JsonResponse({'days': 0, 'error': 'Профиль сотрудника не найден'})

        from datetime import datetime
        start_date = datetime.strptime(start, '%Y-%m-%d').date()
        end_date = datetime.strptime(end, '%Y-%m-%d').date()

        if start_date > end_date:
            return JsonResponse({'days': 0, 'error': 'Некорректный диапазон дат'})

        temp_leave = LeaveRequest(
            start_date=start_date,
            end_date=end_date,
            employee=employee
        )
        days = temp_leave.calculate_working_days()
        return JsonResponse({'days': days})

    except ValueError:
        return JsonResponse({'days': 0, 'error': 'Некорректный формат даты'})
    except Exception as e:
        return JsonResponse({'days': 0, 'error': str(e)})

@login_required
def leave_timeline(request):
    queryset = LeaveRequest.objects.all().select_related(
        'employee__user', 'employee__department__company', 'leave_type'
    )

    company_id = request.GET.get('company')
    department_id = request.GET.get('department')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if company_id:
        queryset = queryset.filter(employee__department__company_id=company_id)
    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if start_date_str:
        queryset = queryset.filter(end_date__gte=parse_date(start_date_str))
    if end_date_str:
        queryset = queryset.filter(start_date__lte=parse_date(end_date_str))

    data = []
    for leave in queryset:
        user = leave.employee.user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        
        data.append({
            'id': leave.id,
            'content': f"{name} ({leave.leave_type.name})",
            'start': leave.start_date.isoformat(),
            'end': leave.end_date.isoformat(),
            'group': leave.employee.department.name if leave.employee.department else 'Без отдела',
            'status': leave.status,
            'className': f"leave-status-{leave.status}" 
        })

    return JsonResponse(data, safe=False)


@login_required
def leave_export_excel(request):
    queryset = LeaveRequest.objects.all().select_related(
        'employee__user', 'employee__department', 'leave_type'
    ).order_by('-start_date')

    company_id = request.GET.get('company')
    department_id = request.GET.get('department')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if company_id:
        queryset = queryset.filter(employee__department__company_id=company_id)
    if department_id:
        queryset = queryset.filter(employee__department_id=department_id)
    if start_date_str:
        queryset = queryset.filter(end_date__gte=parse_date(start_date_str))
    if end_date_str:
        queryset = queryset.filter(start_date__lte=parse_date(end_date_str))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Отпуска"

    headers = ["ФИО сотрудника", "Отдел", "Тип отпуска", "Начало", "Конец", "Дней", "Статус"]
    ws.append(headers)

    for leave in queryset:
        user = leave.employee.user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        dept = leave.employee.department.name if leave.employee.department else "-"
        status_display = dict(LeaveStatusEnum.choices).get(leave.status, leave.status)

        ws.append([
            name,
            dept,
            leave.leave_type.name,
            leave.start_date.strftime("%d.%m.%Y"),
            leave.end_date.strftime("%d.%m.%Y"),
            leave.working_days_count,
            status_display
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="leaves_export.xlsx"'
    
    wb.save(response)
    return response


@need_permission(PermissionEnums.HR)
def vacations(request):
    queryset = Vacation.objects.select_related('employee', 'employee__user').order_by('-start_date', '-id')

    employee_id = request.GET.get('employee')
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    context = {
        'vacations': queryset,
        'selected_employee': employee_id,
    }
    return render(request, 'site/hr/vacations.html', context)


@need_permission(PermissionEnums.HR)
def sick_leaves(request):
    queryset = SickLeave.objects.select_related('employee', 'employee__user').order_by('-start_date', '-id')

    employee_id = request.GET.get('employee')
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    context = {
        'sick_leaves': queryset,
        'selected_employee': employee_id,
    }
    return render(request, 'site/hr/sick_leaves.html', context)


@need_permission(PermissionEnums.HR)
def contracts(request):
    queryset = EmploymentContract.objects.select_related('employee', 'employee__user').order_by('-date', '-id')

    employee_id = request.GET.get('employee')
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    context = {
        'contracts': queryset,
        'selected_employee': employee_id,
    }
    return render(request, 'site/hr/contracts.html', context)

@login_required
def attendance_checkin(request):
    if request.method == 'GET':
        return render(request, 'site/hr/attendance/checkin.html')


    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается. Используйте POST.'}, status=405)

    try:
        data = json.loads(request.body)
        event_type = data.get('event_type')
        photo_base64 = data.get('photo')
        
        ip_address = data.get('ip_address') or request.META.get('REMOTE_ADDR')

        employee = getattr(request.user, 'employee_info', None)
        if not employee:
            return JsonResponse({'error': 'Профиль сотрудника не найден'}, status=403)

        if not event_type or not photo_base64:
            return JsonResponse({'error': 'Не переданы обязательные параметры (event_type, photo)'}, status=400)

        if ';base64,' in photo_base64:
            format_str, imgstr = photo_base64.split(';base64,')
            ext = format_str.split('/')[-1]
        else:
            imgstr = photo_base64
            ext = 'jpg' 

        photo_name = f"checkin_{employee.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        photo_file = ContentFile(base64.b64decode(imgstr), name=photo_name)

        record = AttendanceRecord(
            employee=employee,
            event_type=event_type,
            ip_address=ip_address,
            photo=photo_file
        )
        
        record.full_clean()
        record.save()

        return JsonResponse({'success': True, 'message': 'Отметка успешно сохранена'})

    except ValidationError as e:
        return JsonResponse({'error': e.messages[0]}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"Внутренняя ошибка сервера: {str(e)}"}, status=500)


@login_required
def attendance_journal(request):
    import pytz
    LOCAL_TZ = pytz.timezone('Asia/Almaty')

    user = request.user
    employee = getattr(user, 'employee_info', None)
    
    is_hr = RolePermissions.checkPermission(user.role, PermissionEnums.HR_JOURNAL)
    is_head = employee and employee.head

    if not is_hr and not is_head:
        return redirect('hr:attendance_my')

    target_date_str = request.GET.get('date', date.today().isoformat())
    target_date = parse_date(target_date_str) or date.today()
    
    employees_qs = Employee.objects.filter(status='active').select_related('user', 'department')
    
    if not is_hr and is_head:
        employees_qs = employees_qs.filter(department=employee.department)
    
    department_id = request.GET.get('department')
    if department_id:
        employees_qs = employees_qs.filter(department_id=department_id)

    journal = []
    for emp in employees_qs:
        summary = AttendanceRecord.get_daily_summary(emp, target_date)
        events = summary.get('details', {})
        has_records = len(events) > 0

        late = False
        early_leave = False
        start_dt = None
        end_dt = None

        if has_records:
            start_dt = events.get(CheckInEnum.DAY_START)
            if start_dt:
                local_start = start_dt.astimezone(LOCAL_TZ)
                start_dt = local_start
                if local_start.hour > 9 or (local_start.hour == 9 and local_start.minute > 0):
                    late = True

            end_dt = events.get(CheckInEnum.DAY_END)
            if end_dt:
                local_end = end_dt.astimezone(LOCAL_TZ)
                end_dt = local_end
                if local_end.hour < 18:
                    early_leave = True

        total_work = summary.get('total_work_time', timedelta(0))
        total_hours = total_work.total_seconds() / 3600 if total_work else 0

        journal.append({
            'employee': emp,
            'day_start': start_dt,
            'day_end': end_dt,
            'total_hours': total_hours,
            'late': late,
            'early_leave': early_leave,
            'no_record': not has_records
        })

    departments = Department.objects.all() if is_hr else [employee.department]

    return render(request, 'site/hr/attendance_journal.html', {
        'journal': journal,
        'target_date': target_date,
        'departments': departments,
        'is_hr': is_hr
    })

@login_required
def attendance_my(request):
    import pytz
    LOCAL_TZ = pytz.timezone('Asia/Almaty')

    curr_employee = getattr(request.user, 'employee_info', None)
    
    target_emp_id = request.GET.get('employee_id')
    if target_emp_id:
        is_hr = RolePermissions.checkPermission(request.user.role, PermissionEnums.HR_JOURNAL)
        is_head = curr_employee and curr_employee.head
        
        if is_hr:
            employee = get_object_or_404(Employee, id=target_emp_id)
        elif is_head:
            employee = get_object_or_404(Employee, id=target_emp_id, department=curr_employee.department)
        else:
            return redirect('hr:attendance_my')
    else:
        employee = curr_employee

    if not employee:
        return redirect('dashboard:dashboard')

    try:
        view_month = int(request.GET.get('month', date.today().month))
        view_year = int(request.GET.get('year', date.today().year))
    except ValueError:
        view_month = date.today().month
        view_year = date.today().year

    import calendar as calendar_module
    _, num_days = calendar_module.monthrange(view_year, view_month)
    
    attendance_list = []
    for day in range(num_days, 0, -1):
        current_day = date(view_year, view_month, day)
        if current_day > date.today():
            continue

        summary = AttendanceRecord.get_daily_summary(employee, current_day)
        events = summary.get('details', {})

        late = False
        early_leave = False

        start_dt = events.get(CheckInEnum.DAY_START)
        if start_dt:
            start_dt = start_dt.astimezone(LOCAL_TZ)
            if start_dt.hour > 9 or (start_dt.hour == 9 and start_dt.minute > 0):
                late = True

        end_dt = events.get(CheckInEnum.DAY_END)
        if end_dt:
            end_dt = end_dt.astimezone(LOCAL_TZ)
            if end_dt.hour < 18:
                early_leave = True

        lunch_start = events.get(CheckInEnum.LUNCH_START)
        if lunch_start:
            lunch_start = lunch_start.astimezone(LOCAL_TZ)
        lunch_end = events.get(CheckInEnum.LUNCH_END)
        if lunch_end:
            lunch_end = lunch_end.astimezone(LOCAL_TZ)

        total_hours = summary.get('total_work_time', timedelta(0)).total_seconds() / 3600
        
        attendance_list.append({
            'date': current_day,
            'day_start': start_dt,
            'day_end': end_dt,
            'lunch_start': lunch_start,
            'lunch_end': lunch_end,
            'total_hours': total_hours,
            'late': late,
            'early_leave': early_leave,
            'no_record': len(events) == 0
        })

    prev_month_date = date(view_year, view_month, 1) - timedelta(days=1)
    next_month_date = date(view_year, view_month, 28) + timedelta(days=5)
    
    return render(request, 'site/hr/attendance_my.html', {
        'attendance_list': attendance_list,
        'view_date': date(view_year, view_month, 1),
        'prev_month': prev_month_date,
        'next_month': next_month_date if next_month_date <= date.today() else None,
        'employee': employee,
        'is_own_profile': employee == curr_employee
    })