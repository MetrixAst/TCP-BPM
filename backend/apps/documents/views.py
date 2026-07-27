import json
import logging
import os
from urllib.parse import urlparse

import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect, render
from .models import Document, InnerDocument

from django.shortcuts import render
from account.role_permissions import need_permission, PermissionEnums, RolePermissions

from .forms import InnerDocumentForm
from .enums import DocumentTypeEnum
from .services import documents_list, document, document_action, edit_document_by_type, create_folder
from . import onlyoffice
from . import attachments
from esigner.models import ESignerSigning
from esigner.services import send_for_signing

from project.utils import get_or_error

from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def _onlyoffice_download_url_allowed(download_url):
    parsed = urlparse(download_url)
    configured_host = urlparse(settings.ONLYOFFICE_DS_PUBLIC_URL).hostname
    allowed_hosts = set(getattr(settings, 'ONLYOFFICE_ALLOWED_DOWNLOAD_HOSTS', []))
    if configured_host:
        allowed_hosts.add(configured_host)
    return parsed.scheme in ('http', 'https') and parsed.hostname in allowed_hosts


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
def document_esigner_send(request, pk):
    current = Document.get_by_id(request, pk, exception=True)

    if request.method != 'POST':
        return redirect('documents:document', pk=pk)

    iin = request.POST.get('iin', '').strip()
    if not (iin.isdigit() and len(iin) == 12):
        messages.error(request, 'ИИН/БИН должен состоять из 12 цифр.')
        return redirect('documents:document', pk=pk)
    if not current.document:
        messages.error(request, 'У документа нет файла для подписания.')
        return redirect('documents:document', pk=pk)

    is_company = request.POST.get('is_company') == 'on'
    signers = [{"bin_or_iin": iin, "is_company": is_company}]

    try:
        signing = send_for_signing(current, "document", signers)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('documents:document', pk=pk)
    return redirect(signing.sign_url)


@need_permission(PermissionEnums.DOCUMENTS)
def document_esigner_download(request, pk):
    current = Document.get_by_id(request, pk, exception=True)
    signing = get_object_or_404(
        ESignerSigning,
        content_type=ContentType.objects.get_for_model(current),
        object_id=current.pk,
        status=ESignerSigning.STATUS_COMPLETED,
    )
    if not signing.signed_pdf:
        raise Http404('Подписанный PDF не найден')
    response = FileResponse(
        signing.signed_pdf.open('rb'),
        content_type='application/pdf',
        as_attachment=True,
        filename=f'signed_{current.pk}.pdf',
    )
    response['Cache-Control'] = 'private, no-store'
    return response


@need_permission(PermissionEnums.EDIT_DOCUMENT)
def edit_document(request, document_type, pk):
    return edit_document_by_type(request, pk, document_type)


@need_permission(PermissionEnums.EDIT_DOCUMENT)
def create_folder_view(request, document_type):
    return create_folder(request, document_type)


@need_permission(PermissionEnums.DOCUMENTS)
def document_frame(request, pk):
    current = Document.get_by_id(request, pk)

    context = {
        'document': current,
    }
    return render(request, 'site/documents/document_frame.html', context)


def _user_can_edit_document(request, document):
    """Право редактировать содержимое файла в ONLYOFFICE."""
    if not RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_DOCUMENT):
        return False
    # Редактирует автор или согласующий; наблюдатель — только просмотр.
    if document.author_id == request.user.id:
        return True
    return document.coordinators.filter(id=request.user.id).exists()


@need_permission(PermissionEnums.DOCUMENTS)
def document_editor(request, pk):
    """Полноэкранный редактор/просмотрщик документа через ONLYOFFICE."""
    current = Document.get_by_id(request, pk)

    if not current.document:
        raise Http404('У документа нет файла')

    title = current.title or os.path.basename(current.document.name)
    download_url = current.document.url
    back_url = reverse('documents:document', args=[current.pk])

    if not onlyoffice.is_enabled():
        context = {'title': title, 'download_url': download_url, 'onlyoffice_disabled': True}
        return render(request, 'site/documents/onlyoffice_editor.html', context)

    if not onlyoffice.is_supported(current.document.name):
        context = {'title': title, 'download_url': download_url, 'onlyoffice_unsupported': True}
        return render(request, 'site/documents/onlyoffice_editor.html', context)

    can_edit = _user_can_edit_document(request, current)
    callback_url = reverse('documents:onlyoffice_callback', args=[current.pk])
    config = onlyoffice.build_config(request, current.pk, current.document, title, can_edit, callback_url)

    context = {
        'title': title,
        'download_url': download_url,
        'back_url': back_url,
        'oo_api_url': onlyoffice.public_api_url(),
        'oo_config_json': json.dumps(config, ensure_ascii=False),
        'oo_can_edit': can_edit and onlyoffice.is_editable(current.document.name),
    }
    return render(request, 'site/documents/onlyoffice_editor.html', context)



@csrf_exempt
def onlyoffice_callback(request, pk):
    """Callback Document Server: сохранение отредактированного файла на сервер.

    Эндпойнт вызывает сам Document Server (не браузер), поэтому csrf_exempt и
    проверка по JWT вместо сессии.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 1, 'message': 'Method not allowed'}, status=405)

    document = Document.objects.filter(pk=pk).first()
    if document is None:
        return JsonResponse({'error': 1, 'message': 'Document not found'}, status=404)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 1, 'message': 'Bad payload'}, status=400)

    # Проверка JWT: токен может прийти в теле или в заголовке Authorization.
    if onlyoffice.jwt_enabled():
        token = body.get('token')
        if not token:
            auth = request.headers.get('Authorization', '')
            if auth.startswith('Bearer '):
                token = auth[7:]
        if not token:
            return JsonResponse({'error': 1, 'message': 'Token required'}, status=403)
        try:
            decoded = onlyoffice.decode(token)
            if decoded and 'payload' in decoded:
                decoded = decoded['payload']
            if not decoded:
                raise ValueError('Empty JWT payload')
            body = decoded
        except Exception:
            logger.warning('ONLYOFFICE callback: invalid JWT for document %s', pk)
            return JsonResponse({'error': 1, 'message': 'Invalid token'}, status=403)

    status = body.get('status')
    # 2 — документ готов к сохранению; 6 — принудительное сохранение во время правки.
    if status in (2, 6):
        download_url = body.get('url')
        if download_url:
            if not _onlyoffice_download_url_allowed(download_url):
                return JsonResponse({'error': 1, 'message': 'Download URL not allowed'}, status=403)
            try:
                resp = requests.get(
                    download_url,
                    timeout=getattr(settings, 'ONLYOFFICE_CALLBACK_TIMEOUT', 30),
                )
                resp.raise_for_status()
                filename = (document.document.name or '').split('/')[-1] or f'document_{pk}'
                document.document.save(filename, ContentFile(resp.content), save=True)
            except Exception as exc:
                logger.exception('ONLYOFFICE callback: save failed for document %s: %s', pk, exc)
                return JsonResponse({'error': 1, 'message': 'Save failed'}, status=500)

    return JsonResponse({'error': 0})



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

@need_permission(PermissionEnums.EDIT_DOCUMENT)
def document_file_delete(request, pk, kind, file_pk):
    current = Document.get_by_id(request, pk, exception=True)

    if request.method != 'POST':
        return redirect('documents:document', pk=pk)

    if not _user_can_edit_document(request, current):
        raise Http404

    # Удаление дополнительного файла
    if kind == 'inner':
        inner = current.inner_documents.filter(pk=file_pk).first()
        if inner is None:
            raise Http404

        file_name = inner.document.name if inner.document else ''
        storage = inner.document.storage if inner.document else None

        inner.delete()

        if file_name and storage:
            storage.delete(file_name)

        return redirect('documents:document', pk=pk)

    # Удаление основного файла
    if kind == 'main':
        if not current.document:
            return redirect('documents:document', pk=pk)

        old_file_name = current.document.name
        old_storage = current.document.storage

        # Если есть дополнительные файлы — один из них становится основным,
        # чтобы карточка документа не осталась пустой.
        next_inner = current.inner_documents.first()

        if next_inner and next_inner.document:
            current.document = next_inner.document.name
            current.save(update_fields=['document'])

            next_inner.delete()

            if old_file_name and old_storage:
                old_storage.delete(old_file_name)

        else:
            current.document.delete(save=False)
            current.document = None
            current.save(update_fields=['document'])

        return redirect('documents:document', pk=pk)

    raise Http404


def _universal_editor(request, kind, pk):
    spec = attachments.get_spec(kind)
    if spec is None:
        raise Http404('Неизвестный тип вложения')

    obj = spec.get_object(request, pk)
    if obj is None:
        raise Http404('Вложение не найдено')

    if not spec.can_view(request, obj):
        raise Http404('Вложение не найдено')

    file_field = spec.get_file(obj)
    if not file_field:
        raise Http404('У вложения нет файла')

    title = spec.get_title(obj)
    download_url = file_field.url

    if not onlyoffice.is_enabled():
        context = {'title': title, 'download_url': download_url, 'onlyoffice_disabled': True}
        return render(request, 'site/documents/onlyoffice_editor.html', context)

    if not onlyoffice.is_supported(file_field.name):
        context = {'title': title, 'download_url': download_url, 'onlyoffice_unsupported': True}
        return render(request, 'site/documents/onlyoffice_editor.html', context)

    can_edit = spec.can_edit(request, obj)
    callback_url = reverse('documents:onlyoffice_universal_callback', args=[kind, pk])
    config = onlyoffice.build_config(request, pk, file_field, title, can_edit, callback_url)

    context = {
        'title': title,
        'download_url': download_url,
        'oo_api_url': onlyoffice.public_api_url(),
        'oo_config_json': json.dumps(config, ensure_ascii=False),
        'oo_can_edit': can_edit and onlyoffice.is_editable(file_field.name),
    }
    return render(request, 'site/documents/onlyoffice_editor.html', context)


def attachment_editor(request, kind, pk):
    return _universal_editor(request, kind, pk)


@csrf_exempt
def onlyoffice_universal_callback(request, kind, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 1, 'message': 'Method not allowed'}, status=405)

    spec = attachments.get_spec(kind)
    if spec is None:
        return JsonResponse({'error': 1, 'message': 'Unknown attachment type'}, status=404)

    obj = spec.get_object(request, pk)
    if obj is None:
        return JsonResponse({'error': 1, 'message': 'Attachment not found'}, status=404)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 1, 'message': 'Bad payload'}, status=400)

    if onlyoffice.jwt_enabled():
        token = body.get('token')
        if not token:
            auth = request.headers.get('Authorization', '')
            if auth.startswith('Bearer '):
                token = auth[7:]
        if not token:
            return JsonResponse({'error': 1, 'message': 'Token required'}, status=403)
        try:
            decoded = onlyoffice.decode(token)
            if decoded and 'payload' in decoded:
                decoded = decoded['payload']
            if not decoded:
                raise ValueError('Empty JWT payload')
            body = decoded
        except Exception:
            logger.warning('ONLYOFFICE callback: invalid JWT for %s %s', kind, pk)
            return JsonResponse({'error': 1, 'message': 'Invalid token'}, status=403)

    status = body.get('status')
    if status in (2, 6):
        download_url = body.get('url')
        if download_url:
            if not _onlyoffice_download_url_allowed(download_url):
                return JsonResponse({'error': 1, 'message': 'Download URL not allowed'}, status=403)
            file_field = spec.get_file(obj)
            try:
                resp = requests.get(
                    download_url,
                    timeout=getattr(settings, 'ONLYOFFICE_CALLBACK_TIMEOUT', 30),
                )
                resp.raise_for_status()
                filename = (file_field.name or '').split('/')[-1] or f'{kind}_{pk}'
                file_field.save(filename, ContentFile(resp.content), save=True)
            except Exception as exc:
                logger.exception('ONLYOFFICE callback: save failed for %s %s: %s', kind, pk, exc)
                return JsonResponse({'error': 1, 'message': 'Save failed'}, status=500)

    return JsonResponse({'error': 0})