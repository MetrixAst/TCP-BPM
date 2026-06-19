from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from account.role_permissions import login_required
from account.services.access_scope import user_can_manage_access_scopes

from .forms import CounterpartyTypeForm
from .models import CounterpartyType


def _require_acl_manager(view_func):
    def wrapper(request, *args, **kwargs):
        if not user_can_manage_access_scopes(request.user):
            return HttpResponseForbidden('Недостаточно прав для настройки зон доступа.')
        return view_func(request, *args, **kwargs)

    return wrapper


@login_required
@_require_acl_manager
def counterparty_type_list(request):
    types = CounterpartyType.objects.select_related('access_scope').order_by('sort_order', 'name')
    return render(request, 'site/onec/settings/counterparty_type_list.html', {
        'types': types,
        'title': 'Типы контрагентов и зоны доступа',
    })


@login_required
@_require_acl_manager
def counterparty_type_create(request):
    form = CounterpartyTypeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Тип «{form.instance.name}» создан.')
        return redirect('onec:counterparty_type_list')
    return render(request, 'site/onec/settings/counterparty_type_form.html', {
        'form': form,
        'title': 'Новый тип контрагента',
        'is_edit': False,
    })


@login_required
@_require_acl_manager
def counterparty_type_edit(request, pk):
    counterparty_type = get_object_or_404(CounterpartyType, pk=pk)
    form = CounterpartyTypeForm(request.POST or None, instance=counterparty_type)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Тип контрагента сохранён.')
        return redirect('onec:counterparty_type_list')
    return render(request, 'site/onec/settings/counterparty_type_form.html', {
        'form': form,
        'counterparty_type': counterparty_type,
        'title': 'Редактирование типа',
        'is_edit': True,
    })


@login_required
@_require_acl_manager
def counterparty_type_delete(request, pk):
    counterparty_type = get_object_or_404(CounterpartyType, pk=pk)
    if request.method == 'POST':
        name = counterparty_type.name
        counterparty_type.delete()
        messages.success(request, f'Тип «{name}» удалён.')
        return redirect('onec:counterparty_type_list')
    return render(request, 'site/onec/settings/counterparty_type_confirm_delete.html', {
        'counterparty_type': counterparty_type,
    })
