from django.shortcuts import redirect, render
from django.http import HttpResponseForbidden

from account.role_permissions import RoleEnums, need_permission, PermissionEnums
from project.paginator import CustomPaginator

from .forms import (
    GuestRequistionInitForm,
    TenantRequistionInitForm,
    RequistionInitForm,
    RequistionForm1,
    RequistionForm2,
    RequistionEditForm,
)
from .models import Requistion
from .enums import RequstionTypesEnum


def _portal_context(request):
    tenant = getattr(request.user, 'tenant', None)
    return {
        'is_portal_user': request.user.is_portal_user,
        'portal_tenant': tenant,
    }

@need_permission(PermissionEnums.REQUISTIONS)
def items(request):
    
    queryset = Requistion.get_available_queryset(request)
    page = request.GET.get('page', 1)

    paginator = CustomPaginator(queryset, page)

    context = {
        'paginator': paginator,
        **_portal_context(request),
    }

    return render(request, 'site/requistions/requistions.html', context)



@need_permission(PermissionEnums.REQUISTIONS)
def item(request, pk):

    current = Requistion.get_by_id(request, pk)
    arr = current.get_data()
    
    context = {
        'info': arr,
        'current': current,
        'actions': current.actions(request),
        **_portal_context(request),
    }

    return render(request, 'site/requistions/requistion.html', context)



@need_permission(PermissionEnums.REQUISTIONS)
def item_print(request, pk):

    current = Requistion.get_by_id(request, pk)
    arr = current.get_data()
    
    context = {
        'info': arr,
        'current': current,
    }

    return render(request, 'site/requistions/print.html', context)


@need_permission(PermissionEnums.REQUISTIONS)
def requistion_action(request, pk):
    current = Requistion.get_by_id(request, pk)

    if request.method != 'POST':
        return HttpResponseForbidden('Метод не разрешён')

    action = request.POST.get('action', None)
    text = request.POST.get('text', None)

    # Действие должно быть среди разрешённых текущему пользователю
    # (actions уже отфильтрованы по роли и статусу заявки).
    allowed = {item['action'] for item in current.actions(request)}
    if action not in allowed:
        return HttpResponseForbidden('Действие недоступно')

    if action == "cancel":
        current.delete()
        return redirect('requistions:home')

    current.set_action(request, action, text)

    return redirect('requistions:item', pk=pk)


@need_permission(PermissionEnums.REQUISTIONS)
def create_init(request):
    is_portal = request.user.role in RoleEnums.portal_roles()

    if request.user.role == RoleEnums.TENANT.value:
        form = TenantRequistionInitForm(request.POST or None)
    elif request.user.role == RoleEnums.GUEST.value:
        form = GuestRequistionInitForm(request.POST or None)
    else:
        form = RequistionInitForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            new = form.save(commit=False)
            new.user = request.user
            new.save()
            if hasattr(form, 'save_m2m'):
                form.save_m2m()

            if new.status is None or new.status == "":
                new.set_action(request, "create")

            return redirect('requistions:create_info', pk=new.id)

    context = {
        'form': form,
        'is_portal_user': is_portal,
        **_portal_context(request),
    }

    return render(request, 'site/requistions/create.html', context)



@need_permission(PermissionEnums.REQUISTIONS)
def create_info(request, pk):

    instance = Requistion.get_by_id(request, pk)

    if instance.requistion_type in [RequstionTypesEnum.PERM_PASS.value[0], RequstionTypesEnum.TEMP_PASS.value[0]]:
        form = RequistionForm2(request.POST or None, instance=instance)
    else:
        form = RequistionForm1(request.POST or None, instance=instance)

    if request.method == 'POST':
        if form.is_valid():
            obj = form.save(commit=False)
            if request.user.role == RoleEnums.TENANT.value and request.user.tenant_id:
                if request.user.tenant.room_id and not obj.room:
                    obj.room = request.user.tenant.room.number
                if not obj.name:
                    obj.name = request.user.get_name or request.user.tenant.contact
                if not obj.phone:
                    obj.phone = request.user.tenant.phone
            obj.save()
            return redirect('requistions:home')

    context = {
        'form': form,
        **_portal_context(request),
    }

    return render(request, 'site/requistions/create_info.html', context)


@need_permission(PermissionEnums.REQUISTIONS)
def edit(request, pk):

    # Портал-арендаторы/гости не управляют согласующими и статусом.
    if request.user.role in RoleEnums.portal_roles():
        return HttpResponseForbidden('Действие недоступно')

    instance = Requistion.get_by_id(request, pk)

    form = RequistionEditForm(request.POST or None, instance=instance)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            
            return redirect('requistions:item', pk=pk)

    context = {
        'form': form,
    }

    return render(request, 'site/requistions/edit_requistion.html', context)