from django.shortcuts import redirect, render
from django.http import Http404
from django.db.models import Q
from django.contrib import messages

from project.utils import get_or_error
from project.paginator import CustomPaginator

from .enums import DocumentTypeEnum, DocumentStatusEnum
from .models import Folder, Document
from .forms import DocumentForm, PurchaseForm, BudgetForm, DocumentsForm, InnerDocumentForm
from .folder_structure import ensure_folder_tree, folder_display_name

from account.role_permissions import PermissionEnums, RolePermissions
from account.services.access_scope import (
    filter_folders_queryset,
    get_visible_folder_tree_nodes,
    user_can_manage_access_scopes,
    user_can_view_folder,
)

from datetime import timedelta
from django.utils import timezone


def documents_list(request, document_type, folder=None, status=None):

    root = ensure_folder_tree(document_type)
    visible_folders = filter_folders_queryset(
        root.get_descendants(include_self=True),
        request.user,
    )

    queryset = Document.get_available_queryset(request)
    queryset = queryset.filter(folder__in=visible_folders)

    page = 1
    current_folder = None
    active_folder_ids = []

    if folder is not None and folder != 'all':
        try:
            current_folder = Folder.objects.select_related('access_scope').get(
                pk=folder, tree_id=root.tree_id,
            )
            if not user_can_view_folder(request.user, current_folder):
                raise Http404
            active_folder_ids = list(
                current_folder.get_ancestors(include_self=True).values_list('pk', flat=True)
            )
            folder_ids = filter_folders_queryset(
                current_folder.get_descendants(include_self=True),
                request.user,
            ).values_list('pk', flat=True)
            queryset = queryset.filter(folder_id__in=folder_ids)
        except Folder.DoesNotExist:
            folder = 'all'
    
    if status is not None:
        if status != 'all':
            queryset = queryset.filter(status=status)

    
    #FILTERS
    form = DocumentsForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        filters = form.cleaned_data

        page = filters.get('page', 1)

        #search
        search = filters.get('search', '')
        if search != '':
            queryset = queryset.filter(Q(title__icontains=search) | Q(text__icontains=search) | Q(number__icontains=search))
        
        #supplier
        supplier = filters.get('supplier', None)
        if supplier is not None:
            queryset = queryset.filter(supplier=supplier)

        #date
        date = filters.get('date', '')
        if date is not None:
            queryset = queryset.filter(date__day=date.day, date__month=date.month, date__year=date.year)


    paginator = CustomPaginator(queryset, page)

    context = {
        'document_type': document_type,
        'type_config': DocumentTypeEnum.get_config(document_type),
        'statuses': DocumentStatusEnum.get_full(document_type),
        'tree': get_visible_folder_tree_nodes(request.user, root, include_self=False),
        'can_manage_folder_acl': user_can_manage_access_scopes(request.user),
        'folder': folder,
        'current_folder': current_folder,
        'active_folder_ids': active_folder_ids,
        'status': status,
        'paginator': paginator,
        'can_create': RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_DOCUMENT),
        'form': form,
    }

    return render(request, 'site/documents/documents.html', context)


def create_folder(request, document_type):
    """Создание новой папки в дереве документооборота/закупок."""
    root = ensure_folder_tree(document_type)

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        parent_id = request.POST.get('parent') or None

        if not name:
            messages.error(request, 'Укажите название папки.')
            return redirect('documents:list', document_type=document_type)

        parent = root
        if parent_id:
            parent = Folder.objects.filter(
                pk=parent_id, tree_id=root.tree_id,
            ).first() or root

        # Имя папки уникально на уровне модели — префиксуем корнем и снимаем коллизии.
        base_name = f'{root.name} / {name}'
        full_name = base_name
        suffix = 2
        while Folder.objects.filter(name=full_name).exists():
            full_name = f'{base_name} ({suffix})'
            suffix += 1

        folder = Folder.objects.create(
            name=full_name,
            parent=parent,
            access_scope=parent.access_scope,
        )
        messages.success(request, f'Папка «{folder.short_name}» создана.')

    return redirect('documents:list', document_type=document_type)


def document(request, pk):
    current = Document.get_by_id(request, pk)
    if not user_can_view_folder(request.user, current.folder):
        raise Http404
    context = {
        'document': current,
        'status_info': current.status_info,
        'actions': current.actions(request),
        'type_config': DocumentTypeEnum.get_config(current.document_type),
        'addit_form': InnerDocumentForm(),
    }

    return render(request, 'site/documents/document.html', context)


def document_action(request, pk):
    current = Document.get_by_id(request, pk)
    document_type = current.document_type

    action = request.POST.get('action', None)
    text = request.POST.get('text', None)

    if action == "cancel":
        current.delete()
        return redirect('documents:list', document_type=document_type)
    
    current.set_action(request, action, text)


    return redirect('documents:document', pk=pk)


def edit_document_by_type(request, pk, document_type):
    current = Document.get_by_id(request, pk, exception=False)
    if current is not None and current.author != request.user:
        raise Http404
    
    if document_type == DocumentTypeEnum.PURCHASES.value[0]:
        form_class = PurchaseForm
    elif document_type == DocumentTypeEnum.BUDGET.value[0]:
        form_class = BudgetForm
    else:
        form_class = DocumentForm

    form = form_class(
        instance=current,
        data=request.POST or None,
        files=request.FILES or None,
        user=request.user,
    )

    if request.method == 'POST':
        if form.is_valid():
            new = form.save(commit=False)
            new.author = request.user
            new.document_type = document_type

            if document_type == DocumentTypeEnum.DOCUMENTS.value[0]:
                if not new.reg_date:
                    new.reg_date = timezone.localdate()
                new.need_all = False
                new.need_head = False
            elif new.end_date is None:
                days = form.cleaned_data.get('days', 4)
                new.end_date = timezone.now() + timedelta(days=days)

            new.save()

            if document_type == DocumentTypeEnum.DOCUMENTS.value[0]:
                if not new.number:
                    new.number = f'DOC-{new.pk:05d}'
                    new.save(update_fields=['number'])
                new.coordinators.set([request.user])
                new.observers.set([request.user])
            else:
                form.save_m2m()

            if new.status is None or new.status == "":
                new.set_action(request, "create")

            return redirect('documents:document', pk=new.pk)

    context = {
        'document_type': document_type,
        'form': form,
        'type_config': DocumentTypeEnum.get_config(document_type),
    }

    return render(request, 'site/documents/edit_document.html', context)



