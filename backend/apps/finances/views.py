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