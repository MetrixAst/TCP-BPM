from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.db.models import Q


from project.utils import get_or_none, get_or_error
from project.paginator import CustomPaginator

from account.role_permissions import need_permission, PermissionEnums
from account.models import Employee
from account.forms import EmployeeForm

from .forms import CalendarItemForm, EmployeeCreationForm, EmployeesListForm
from .models import CalendarItem
from .serializers import CalendarItemSerializer
from .enums import CalendarItemType
from .models import CalendarItem, Company, Position, Vacation, SickLeave, EmploymentContract

@need_permission(PermissionEnums.HR)
def structure(request):
    return render(request, 'site/hr/org.html')


#EMPLOYEES
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

    employee = get_or_error(Employee, pk=pk)

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


#CALENDAR

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