from django.shortcuts import redirect, render
from account.role_permissions import need_permission, PermissionEnums
from django.http import JsonResponse

from project.utils import get_or_none

from .forms import FinanceItemForm
from .models import FinanceItem, TenantPaymentRegistry
from .serializers import FinanceItemSerializer

from datetime import date
from django.db.models import Q



def payment_reg(request):
    context = {

    }

    return render(request, 'site/finances/payment_register.html', context)



@need_permission(PermissionEnums.FINANCES)
def calendar(request):
    context = {

    }

    return render(request, 'site/finances/calendar.html', context)


@need_permission(PermissionEnums.FINANCES)
def calendar_action(request, action):

    if action == 'json':
        qs = FinanceItem.objects.all()
        res = FinanceItemSerializer(qs, many=True)

        return JsonResponse(res.data, safe=False)

    if request.method == 'POST':
        pk = request.POST.get('id', None)
        instance = None
        if pk is not None:
            instance = get_or_none(FinanceItem, pk=pk)

        if action == 'delete':
            instance.delete()

            return JsonResponse({})
        else:
            form = FinanceItemForm(request.POST, instance=instance)
            if form.is_valid():
                new = form.save(commit=False)
                new.user = request.user
                new.save()

                res = FinanceItemSerializer(new)

                return JsonResponse(res.data)

    return JsonResponse({}, status=400)



def budget_list(request):
    context = {

    }

    return render(request, 'site/finances/budget/budget_list.html', context)


def budget(request, pk):
    context = {

    }

    return render(request, 'site/finances/budget/budget.html', context)


def budget_create(request):
    context = {

    }

    return render(request, 'site/finances/budget/budget_create.html', context)


def bill(request):
    context = {

    }

    return render(request, 'site/finances/bill.html', context)


@need_permission(PermissionEnums.FINANCES)
def payment_reg(request):
    qs = TenantPaymentRegistry.objects.select_related(
        'tenant', 'tenant__category', 'tenant__room'
    ).order_by('-period', 'tenant__name')

    search      = request.GET.get('search', '').strip()
    status      = request.GET.get('status', '')
    period_from = request.GET.get('period_from', '')
    period_to   = request.GET.get('period_to', '')
    tenant_id   = request.GET.get('tenant', '')

    if search:
        qs = qs.filter(
            Q(tenant__name__icontains=search) |
            Q(contract_number__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if period_from:
        try:
            qs = qs.filter(period__gte=period_from)
        except Exception:
            pass
    if period_to:
        try:
            qs = qs.filter(period__lte=period_to)
        except Exception:
            pass

    STATUS_COLORS = {
        TenantPaymentRegistry.Status.PAID: 'success',
        TenantPaymentRegistry.Status.PARTIAL: 'warning',
        TenantPaymentRegistry.Status.PENDING: 'info',
        TenantPaymentRegistry.Status.OVERDUE: 'danger',
        TenantPaymentRegistry.Status.CANCELLED: 'secondary',
    }

    entries = []
    for entry in qs:
        entries.append({
            'obj':   entry,
            'color': STATUS_COLORS.get(entry.status, 'secondary'),
        })

    from tenants.models import Tenant
    tenants  = Tenant.objects.order_by('name')
    statuses = TenantPaymentRegistry.Status.choices

    context = {
        'entries': entries,
        'tenants': tenants,
        'statuses': statuses,
        'today': date.today(),

        'f_search': search,
        'f_status': status,
        'f_tenant': tenant_id,
        'f_period_from': period_from,
        'f_period_to': period_to,
    }

    return render(request, 'site/finances/payment_register.html', context)

@need_permission(PermissionEnums.FINANCES)
def payment_calendar(request):
    from datetime import date, timedelta
    from calendar import monthrange
    from .models import PaymentCalendarEntry
    from tenants.models import Tenant

    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    tenant_id = request.GET.get('tenant', '')
    status    = request.GET.get('status', '')

    qs = PaymentCalendarEntry.objects.select_related(
        'tenant', 'tenant__room'
    ).filter(
        expected_date__year=year,
        expected_date__month=month,
    ).order_by('expected_date', 'tenant__name')

    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if status:
        qs = qs.filter(status=status)

    days_in_month = monthrange(year, month)[1]
    calendar_days = []

    for day in range(1, days_in_month + 1):
        day_date    = date(year, month, day)
        day_entries = [e for e in qs if e.expected_date == day_date]

        planned = sum(e.expected_amount for e in day_entries)
        actual  = sum(e.actual_amount   for e in day_entries)

        calendar_days.append({
            'date':       day_date,
            'entries':    day_entries,
            'count':      len(day_entries),
            'planned':    planned,
            'actual':     actual,
            'is_today':   day_date == today,
            'is_weekend': day_date.weekday() >= 5,
            'has_overdue': any(e.status == 'overdue' for e in day_entries),
        })

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        'calendar_days': calendar_days,
        'tenants':       Tenant.objects.order_by('name'),
        'statuses':      PaymentCalendarEntry.Status.choices,
        'year':          year,
        'month':         month,
        'month_name':    _month_name(month),
        'prev_year':     prev_year,
        'prev_month':    prev_month,
        'next_year':     next_year,
        'next_month':    next_month,
        'today':         today,
        'f_tenant':      tenant_id,
        'f_status':      status,
    }

    return render(request, 'site/finances/payment_calendar.html', context)


@need_permission(PermissionEnums.FINANCES)
def payment_calendar_day(request, year, month, day):
    from datetime import date
    from .models import PaymentCalendarEntry

    try:
        day_date = date(year, month, day)
    except ValueError:
        from django.http import Http404
        raise Http404

    entries = PaymentCalendarEntry.objects.select_related(
        'tenant', 'tenant__room'
    ).filter(expected_date=day_date).order_by('tenant__name')

    STATUS_COLORS = {
        PaymentCalendarEntry.Status.PLAN:    'info',
        PaymentCalendarEntry.Status.FACT:    'success',
        PaymentCalendarEntry.Status.OVERDUE: 'danger',
    }

    rows = [
        {'obj': e, 'color': STATUS_COLORS.get(e.status, 'secondary')}
        for e in entries
    ]

    total_planned = sum(e.expected_amount for e in entries)
    total_actual  = sum(e.actual_amount   for e in entries)

    context = {
        'day_date':     day_date,
        'rows':         rows,
        'total_planned': total_planned,
        'total_actual':  total_actual,
        'diff':          total_actual - total_planned,
    }

    return render(request, 'site/finances/payment_calendar_day.html', context)


def _month_name(month):
    names = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель',
        'Май', 'Июнь', 'Июль', 'Август',
        'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ]
    return names[month]