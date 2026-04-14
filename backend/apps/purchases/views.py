from django.shortcuts import redirect, render
from django.db.models import Q
from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from .forms import SupplierForm
from .models import Supplier
from project.utils import get_or_error, get_or_none
from project.paginator import CustomPaginator

from .enums import SupplierStatusEnum


@need_permission(PermissionEnums.SUPPLIERS)
def suppliers(request):
    return suppliers_by_status(request)


@need_permission(PermissionEnums.SUPPLIERS)
def suppliers_by_status(request, status = None):

    queryset = Supplier.objects.all()
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))

    statuses = SupplierStatusEnum.list()
    statuses.insert(0, ('all', 'Все'))

    if search != '':
        queryset = queryset.filter(Q(name__icontains=search) | Q(identifier__icontains=search))

    if status is not None and status != 'all':
        queryset = queryset.filter(status=status)

    paginator = CustomPaginator(queryset, page)

    context = {
        'paginator': paginator,
        'statuses': statuses,
        'status': status,
    }

    return render(request, 'site/purchases/suppliers/suppliers.html', context)


@need_permission(PermissionEnums.SUPPLIERS)
def supplier(request, pk):
    current = get_or_error(Supplier, id=pk)

    arr = {
        "ID": current.id,
        "Дата добавления": current.created_at,
        "Дата обновления": current.updated_at,
        "Создано": current.author.get_name,
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

    context = {
        'supplier': current,
        'info': arr,
    }

    return render(request, 'site/purchases/suppliers/supplier.html', context)



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