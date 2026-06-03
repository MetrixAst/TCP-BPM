from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from account.role_permissions import login_required, RoleEnums
from onec.models import CounterpartyType, AccessScope, Counterparty
from account.models import UserAccount, Department


def _can_manage(user):
    role = user.role.value if hasattr(user.role, 'value') else user.role
    return role in (RoleEnums.ADMINISTRATOR.value, RoleEnums.OWNER.value)


@login_required
def counterparty_types(request):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('<h1>403</h1><p>Доступ только для администраторов.</p>')

    types = CounterpartyType.objects.all().prefetch_related('counterparties')
    return render(request, 'site/settings/counterparty_types.html', {
        'counterparty_types': types,
    })


@login_required
def counterparty_type_create(request):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()

        if not name or not code:
            messages.error(request, 'Заполните название и код.')
            return redirect('settings:counterparty_types')

        if CounterpartyType.objects.filter(code=code).exists():
            messages.error(request, f'Тип с кодом «{code}» уже существует.')
            return redirect('settings:counterparty_types')

        CounterpartyType.objects.create(name=name, code=code)
        messages.success(request, f'Тип «{name}» создан.')

    return redirect('settings:counterparty_types')


@login_required
def counterparty_type_edit(request, pk):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    ct = get_object_or_404(CounterpartyType, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()

        if not name or not code:
            messages.error(request, 'Заполните название и код.')
            return redirect('settings:counterparty_types')

        if CounterpartyType.objects.filter(code=code).exclude(pk=pk).exists():
            messages.error(request, f'Код «{code}» уже занят.')
            return redirect('settings:counterparty_types')

        ct.name = name
        ct.code = code
        ct.save()
        messages.success(request, f'Тип «{name}» обновлён.')

    return redirect('settings:counterparty_types')


@login_required
def counterparty_type_delete(request, pk):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    ct = get_object_or_404(CounterpartyType, pk=pk)
    if request.method == 'POST':
        name = ct.name
        ct.delete()
        messages.success(request, f'Тип «{name}» удалён.')
    return redirect('settings:counterparty_types')


@login_required
def counterparty_access(request):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('<h1>403</h1><p>Доступ только для администраторов.</p>')

    scopes = AccessScope.objects.prefetch_related(
        'users', 'departments', 'counterparty_types', 'counterparties'
    ).all()

    role_choices = [
        (RoleEnums.STAFF.value,            'Сотрудник'),
        (RoleEnums.HR.value,               'HR-менеджер'),
        (RoleEnums.CHIEF_ACCOUNTANT.value, 'Главный бухгалтер'),
        (RoleEnums.CFO.value,              'CFO'),
        (RoleEnums.ADMINISTRATOR.value,    'Администратор'),
        (RoleEnums.OWNER.value,            'Владелец'),
    ]

    return render(request, 'site/settings/counterparty_access.html', {
        'access_scopes':      scopes,
        'counterparty_types': CounterpartyType.objects.all(),
        'role_choices':       role_choices,
        'departments':        Department.objects.all().order_by('name'),
        'users':              UserAccount.objects.filter(is_active=True).order_by('first_name', 'last_name'),
    })


@login_required
def access_scope_create(request):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Укажите название зоны.')
            return redirect('settings:counterparty_access')

        scope = AccessScope.objects.create(
            name=name,
            roles=request.POST.getlist('roles'),
        )
        scope.departments.set(request.POST.getlist('departments'))
        scope.counterparty_types.set(request.POST.getlist('counterparty_types'))
        scope.users.set(request.POST.getlist('users'))
        messages.success(request, f'Зона доступа «{name}» создана.')

    return redirect('settings:counterparty_access')


@login_required
def access_scope_delete(request, pk):
    if not _can_manage(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    scope = get_object_or_404(AccessScope, pk=pk)
    if request.method == 'POST':
        name = scope.name
        scope.delete()
        messages.success(request, f'Зона «{name}» удалена.')
    return redirect('settings:counterparty_access')
