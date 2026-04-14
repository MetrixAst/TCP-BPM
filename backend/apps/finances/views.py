from django.shortcuts import redirect, render
from account.role_permissions import need_permission, PermissionEnums
from django.http import JsonResponse

from project.utils import get_or_none

from .forms import FinanceItemForm
from .models import FinanceItem
from .serializers import FinanceItemSerializer


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