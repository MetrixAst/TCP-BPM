from django.shortcuts import redirect, render
from django.http import Http404
from django.db.models import Q

from project.utils import get_or_error
from project.paginator import CustomPaginator

from .enums import DocumentTypeEnum, DocumentStatusEnum
from .models import Folder, Document
from .forms import DocumentForm, PurchaseForm, BudgetForm, DocumentsForm, InnerDocumentForm

from account.role_permissions import PermissionEnums, RolePermissions

from datetime import timedelta
from django.utils import timezone


def documents_list(request, document_type, folder = None, status = None):

    root = get_or_error(Folder, root_type=document_type)
    folders = root.get_descendants(include_self=True)

    queryset = Document.get_available_queryset(request)
    queryset = queryset.filter(folder__in=folders)
    
    page = 1

    if folder is not None:
        if folder != 'all':
            queryset = queryset.filter(folder_id=folder)
    
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
        
        #coordinators
        coordinator = filters.get('coordinator', '')
        if coordinator != '':
            queryset = queryset.filter(coordinators=coordinator)

        



    paginator = CustomPaginator(queryset, page)

    context = {
        'document_type': document_type,
        'type_config': DocumentTypeEnum.get_config(document_type),
        'statuses': DocumentStatusEnum.get_full(document_type),
        'tree': root.get_descendants(include_self=False),
        'folder': folder,
        'status': status,
        'paginator': paginator,
        'can_create': RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_DOCUMENT),
        'form': form,
    }

    return render(request, 'site/documents/documents.html', context)


def document(request, pk):
    current = Document.get_by_id(request, pk)
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
    
    template = 'site/documents/edit_document.html'

    if document_type == DocumentTypeEnum.PURCHASES.value[0]:
        form_class = PurchaseForm
    elif document_type == DocumentTypeEnum.BUDGET.value[0]:
        form_class = BudgetForm
        template = 'site/documents/edit_budget.html'
    else:
        form_class = DocumentForm

    form = form_class(instance=current, data=request.POST or None, files=request.FILES or None)

    if request.method == 'POST':
        if form.is_valid():
            new = form.save(commit=False)
            new.author = request.user
            new.document_type = document_type

            if new.end_date is None:
                days = form.cleaned_data.get('days', 4)
                new.end_date = timezone.now() + timedelta(days=days)

            new.save()
            form.save_m2m()

            if new.status is None or new.status == "": #if is NEW
                new.set_action(request, "create")
            
            return redirect('documents:document', pk=new.pk)

    context = {
        'document_type': document_type,
        'form': form,
    }

    return render(request, template, context)



