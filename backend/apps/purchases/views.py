from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.http import Http404
from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from account.services.access_scope import filter_suppliers_queryset, user_can_view_supplier
from .forms import SupplierForm
from .models import Supplier
from project.utils import get_or_error, get_or_none
from project.paginator import CustomPaginator
from addits.models import Comment

from .enums import SupplierStatusEnum
from .services.sync_from_onec import sync_counterparties_to_suppliers


@need_permission(PermissionEnums.SUPPLIERS)
def suppliers(request):
    return suppliers_by_status(request)


@need_permission(PermissionEnums.SUPPLIERS)
def suppliers_by_status(request, status=None):

    sync_counterparties_to_suppliers()

    # Статус можно передать и через URL-path (/suppliers/active/),
    # и через GET-параметр (?status=active) — для кастомного дропдауна.
    if status is None:
        status = request.GET.get('status', 'all') or 'all'

    show_archived = request.GET.get('archived') == '1'
    queryset = filter_suppliers_queryset(
        Supplier.objects.filter(is_active=not show_archived), request.user,
    )
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))

    statuses = SupplierStatusEnum.list()
    statuses.insert(0, ('all', 'Все'))

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(identifier__icontains=search)
        )

    if status and status != 'all':
        queryset = queryset.filter(status=status)

    paginator = CustomPaginator(queryset, page)

    from account.services.access_scope import user_can_manage_access_scopes
    context = {
        'paginator': paginator,
        'statuses': statuses,
        'status': status,
        'can_manage_acl': user_can_manage_access_scopes(request.user),
        'show_archived': show_archived,
        'archived_count': filter_suppliers_queryset(
            Supplier.objects.filter(is_active=False), request.user,
        ).count(),
    }

    return render(request, 'site/purchases/suppliers/suppliers.html', context)


@need_permission(PermissionEnums.SUPPLIERS)
def supplier(request, pk):
    current = get_or_error(Supplier, id=pk)

    if not user_can_view_supplier(request.user, current):
        raise Http404

    arr = {
        "ID": current.id,
        "Дата добавления": current.created_at,
        "Дата обновления": current.updated_at,
        "Создано": current.author.get_name if current.author else "—",
        "Статус контрагента": current.get_status_display,
        "Благонадежность": current.get_check_status_display,
        "Форма собственности": current.get_form_display,
        "Город": current.city,
        "Юр. / физ. лицо": current.get_supplier_type_display,
        "Дата регистрации ТОО/ИП": current.reg_date,
        "БИН / ИИН": current.identifier,
        "Категория контрагента": current.categories_list,
        "КБЕ": current.kbe,
        "Страна резидентства": current.country,
        "Юридический адрес": current.address1,
        "Фактический адрес": current.address2,
        "ФИО учредителя": current.head_name,
        "Статус учредителя": current.head_status,
        "Телефон": current.phone,
        "Email": current.email,
        "Серия свидетельства по НДС": current.certificate_serie,
        "Номер свидетельства по НДС": current.certificate_number,
        "Дата свидетельства по НДС": current.certificate_date,
        "Контакты": current.contacts,
        "Ссылка на карточку контраганта в adata.kz": current.adata_link,
        "Основной окэд": current.oked,
        "Полное наименование": current.name,
        "Есть проблемы": current.problems,
        "Размер предприятия": current.size,
        "Юрист": current.lawyer,
    }

    comments = Comment.objects.filter(
        target_type='supplier', target_id=current.id
    ).select_related('user').order_by('id')
    
    from account.services.permissions import user_has_permission
    return render(request, 'site/purchases/suppliers/supplier.html', {
        'supplier': current,
        'info': arr,
        'comments': comments,
        'can_edit': user_has_permission(request.user, PermissionEnums.EDIT_SUPPLIERS),
    })


@need_permission(PermissionEnums.EDIT_SUPPLIERS)
def edit_supplier(request, pk):
    current = get_or_none(Supplier, id=pk)
    form = SupplierForm(instance=current)

    if request.method == 'POST':
        form = SupplierForm(instance=current, data=request.POST)
        if form.is_valid():
            new = form.save(commit=False)
            if new.author is None:
                new.author = request.user
            new.save()
            form.save_m2m()

            return redirect('purchases:suppliers')

    context = {
        'form': form,
    }

    return render(request, 'site/purchases/suppliers/edit_supplier.html', context)

@need_permission(PermissionEnums.EDIT_SUPPLIERS)
@require_POST
def delete_supplier(request, pk):
    from django.db.models import ProtectedError

    current = get_or_error(Supplier, id=pk)
    if not user_can_view_supplier(request.user, current):
        raise Http404
    if current.onec_id:
        # Запись из 1С вернётся при следующей синхронизации — только архив.
        messages.error(request, f'«{current.name}» загружен из 1С — его можно только перенести в архив.')
        return redirect('purchases:supplier', pk=pk)

    name = current.name
    try:
        current.delete()
    except ProtectedError:
        messages.error(request, f'Нельзя удалить «{name}»: есть связанные документы. Перенесите карточку в архив.')
        return redirect('purchases:supplier', pk=pk)

    messages.success(request, f'Контрагент «{name}» удалён.')
    return redirect('purchases:suppliers')


@need_permission(PermissionEnums.EDIT_SUPPLIERS)
@require_POST
def toggle_supplier_archive(request, pk):
    current = get_or_error(Supplier, id=pk)
    if not user_can_view_supplier(request.user, current):
        raise Http404
    current.is_active = not current.is_active
    current.save(update_fields=['is_active', 'updated_at'])
    if current.is_active:
        messages.success(request, f'Контрагент «{current.name}» возвращён из архива.')
    else:
        messages.success(request, f'Контрагент «{current.name}» перенесён в архив.')
    return redirect('purchases:supplier', pk=pk)


@need_permission(PermissionEnums.EDIT_SUPPLIERS)
def import_suppliers_view(request):
    from django.http import HttpResponse
    from project.excel_import import import_suppliers, supplier_template

    if request.GET.get('template'):
        response = HttpResponse(
            supplier_template(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename=counterparties_import_template.xlsx'
        return response

    result = None
    if request.method == 'POST' and request.FILES.get('file'):
        try:
            result = import_suppliers(request.FILES['file'], author=request.user)
        except Exception:
            messages.error(request, 'Не удалось прочитать файл. Загрузите .xlsx по шаблону.')
        else:
            if result.ok:
                messages.success(
                    request,
                    f'Импорт завершён: добавлено {result.created}, обновлено {result.updated}.',
                )
                return redirect('purchases:suppliers')

    return render(request, 'site/import_excel.html', {
        'title': 'Импорт контрагентов',
        'back_url': 'purchases:suppliers',
        'template_url': request.path + '?template=1',
        'hint': 'Контрагент с тем же БИН/ИИН (или названием) будет обновлён. Новые получают статус «На модерации».',
        'result': result,
    })
