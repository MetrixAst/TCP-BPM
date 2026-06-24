from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from account.role_permissions import need_permission, PermissionEnums
from account.services.access_scope import user_can_manage_access_scopes

from .enums import DocumentTypeEnum
from .folder_structure import ensure_folder_tree
from .forms_acl import FolderAccessForm
from .models import Folder
from account.i18n import translate


def _require_acl_manager(view_func):
    def wrapper(request, *args, **kwargs):
        if not user_can_manage_access_scopes(request.user):
            return HttpResponseForbidden('Недостаточно прав для настройки доступа к папкам.')
        return view_func(request, *args, **kwargs)

    return wrapper


@need_permission(PermissionEnums.DOCUMENTS)
@_require_acl_manager
def folder_access_list(request, document_type):
    if DocumentTypeEnum.get_config(document_type) is None:
        return HttpResponseForbidden()

    root = ensure_folder_tree(document_type)
    folders = root.get_descendants(include_self=True).select_related('access_scope').order_by('tree_id', 'lft')

    return render(request, 'site/documents/settings/folder_access_list.html', {
        'document_type': document_type,
        'type_config': DocumentTypeEnum.get_config(document_type),
        'folders': folders,
        'title': translate(getattr(request, 'current_lang', 'ru'), 'documents.folder_access', default='Доступ к папкам'),
    })


@need_permission(PermissionEnums.DOCUMENTS)
@_require_acl_manager
def folder_access_edit(request, document_type, pk):
    if DocumentTypeEnum.get_config(document_type) is None:
        return HttpResponseForbidden()

    root = ensure_folder_tree(document_type)
    folder = get_object_or_404(
        root.get_descendants(include_self=True).select_related('access_scope'),
        pk=pk,
    )
    form = FolderAccessForm(folder, request.POST or None)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Доступ для папки «{folder.short_name}» сохранён.')
        return redirect('documents:folder_access_list', document_type=document_type)

    return render(request, 'site/documents/settings/folder_access_form.html', {
        'document_type': document_type,
        'type_config': DocumentTypeEnum.get_config(document_type),
        'folder': folder,
        'form': form,
        'title': f'{translate(getattr(request, "current_lang", "ru"), "documents.access", default="Доступ")}: {folder.short_name}',
    })
