from django.shortcuts import redirect, render
from .models import Document, InnerDocument

from django.shortcuts import render
from account.role_permissions import need_permission, PermissionEnums

from .forms import InnerDocumentForm
from .enums import DocumentTypeEnum
from .services import documents_list, document, document_action, edit_document_by_type

from project.utils import get_or_error

from django.http import Http404

@need_permission(PermissionEnums.DOCUMENTS)
def documents(request, document_type):
    return documents_list(request, document_type, folder='all', status='all')


@need_permission(PermissionEnums.DOCUMENTS)
def documents_folder_list(request, document_type, folder):
    return documents_list(request, document_type, folder=folder)


@need_permission(PermissionEnums.DOCUMENTS)
def documents_status_list(request, document_type, status):
    return documents_list(request, document_type, status=status)


@need_permission(PermissionEnums.DOCUMENTS)
def document_view(request, pk):
    return document(request, pk)


@need_permission(PermissionEnums.DOCUMENTS)
def document_action_view(request, pk):
    return document_action(request, pk)


@need_permission(PermissionEnums.EDIT_DOCUMENT)
def edit_document(request, document_type, pk):
    return edit_document_by_type(request, pk, document_type)


@need_permission(PermissionEnums.DOCUMENTS)
def document_frame(request, pk):
    current = Document.get_by_id(request, pk)

    context = {
        'document': current,
    }
    return render(request, 'site/documents/document_frame.html', context)



@need_permission(PermissionEnums.DOCUMENTS)
def addit_document_frame(request, pk):
    current = get_or_error(InnerDocument, pk=pk)

    context = {
        'document': current,
    }
    return render(request, 'site/documents/addit_document.html', context)


@need_permission(PermissionEnums.EDIT_DOCUMENT)
def upload_addit_document(request, pk):
    current = Document.get_by_id(request, pk, exception=True)

    form = InnerDocumentForm(data=request.POST or None, files=request.FILES or None)

    if request.method == 'POST':
        if form.is_valid():
            new = form.save(commit=False)
            new.author = request.user
            new.parent = current
            new.save()

    return redirect('documents:document', pk=pk)