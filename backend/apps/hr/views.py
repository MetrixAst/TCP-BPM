import openpyxl
from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.db import transaction
from django.utils.dateparse import parse_date
from datetime import datetime

from project.utils import get_or_none, get_or_error
from project.paginator import CustomPaginator

from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from account.models import Employee
from account.forms import EmployeeForm

from .forms import (
    CalendarItemForm, EmployeeCreationForm, EmployeesListForm, 
    LeaveFilterForm, LeaveRequestForm
)
from .models import (
    CalendarItem, Company, Position, LeaveRequest, 
    LeaveType, Vacation, SickLeave, EmploymentContract
)
from .serializers import CalendarItemSerializer
from .enums import CalendarItemType, LeaveStatusEnum


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

