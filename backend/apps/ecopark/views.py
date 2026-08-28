import json
import os
from django.http import Http404, JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from documents import onlyoffice
from django.shortcuts import redirect, render, get_object_or_404
import secrets
from django.utils import timezone
from django.template.loader import render_to_string
from .models import (
    EcoObject, EcoExecutor, EcoWork,
    RoundPoint, ChecklistTemplate, ChecklistItem, Equipment,
    RoundVisit, RoundVisitAnswer, Defect,
)


def _fmt_amount(value):
    return f'{int(value):,}'.replace(',', ' ')


def home(request):
    works = EcoWork.objects.select_related('eco_object', 'executor').all()

    obj_filter = request.GET.get('object')
    exec_filter = request.GET.get('executor')
    status_filter = request.GET.get('status')

    # Фильтруем по имени (строке), а не по id — иначе ValueError
    if obj_filter:
        works = works.filter(eco_object__name=obj_filter)
    if exec_filter:
        works = works.filter(executor__name=exec_filter)
    if status_filter:
        works = works.filter(status=status_filter)

    all_works = EcoWork.objects.all()
    kpi = {
        'total': all_works.count(),
        'done': all_works.filter(status='done').count(),
        'progress': all_works.filter(status='progress').count(),
        'total_sum_fmt': _fmt_amount(sum(w.amount for w in all_works)),
    }

    context = {
        'works': works,
        'kpi': kpi,
        'objects': EcoObject.objects.filter(is_active=True),
        'executors': EcoExecutor.objects.filter(is_active=True),
    }
    return render(request, 'site/ecopark/ecopark.html', context)


def item(request, pk):
    work = get_object_or_404(
        EcoWork.objects.select_related('eco_object', 'executor'), pk=pk
    )
    history = EcoWork.objects.select_related('eco_object', 'executor').filter(
        eco_object=work.eco_object
    ).exclude(pk=pk).order_by('-date')

    context = {
        'work': work,
        'history': history,
    }
    return render(request, 'site/ecopark/ecopark_item.html', context)


def create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        object_id = request.POST.get('object')
        executor_id = request.POST.get('executor')
        responsible = request.POST.get('responsible')
        amount = request.POST.get('amount') or 0
        status = request.POST.get('status', 'pending')
        document = request.FILES.get('document')

        EcoWork.objects.create(
            title=title,
            eco_object_id=object_id or None,
            executor_id=executor_id or None,
            responsible=responsible,
            amount=amount,
            status=status,
            document=document,
        )
        return redirect('ecopark:home')

    context = {
        'objects': EcoObject.objects.filter(is_active=True),
        'executors': EcoExecutor.objects.filter(is_active=True),
    }
    return render(request, 'site/ecopark/ecopark_create.html', context)


def work_editor(request, pk):
    work = get_object_or_404(EcoWork, pk=pk)
    if not work.document:
        raise Http404('У работы нет файла')
    title = work.title or os.path.basename(work.document.name)
    download_url = work.document.url
    back_url = reverse('ecopark:item', args=[pk])

    if not onlyoffice.is_enabled():
        return render(request, 'site/documents/onlyoffice_editor.html', {
            'title': title, 'download_url': download_url, 'onlyoffice_disabled': True
        })

    if not onlyoffice.is_supported(work.document.name):
        return render(request, 'site/documents/onlyoffice_editor.html', {
            'title': title, 'download_url': download_url, 'onlyoffice_unsupported': True
        })

    callback_url = reverse('ecopark:work_editor_callback', args=[pk])
    config = onlyoffice.build_config(request, pk, work.document, title, False, callback_url)

    return render(request, 'site/documents/onlyoffice_editor.html', {
        'title': title,
        'download_url': download_url,
        'back_url': back_url,
        'oo_api_url': onlyoffice.public_api_url(),
        'oo_config_json': json.dumps(config, ensure_ascii=False),
        'oo_can_edit': False,
    })


@csrf_exempt
def work_editor_callback(request, pk):
    return JsonResponse({'error': 0})


def edit(request, pk):
    work = get_object_or_404(EcoWork, pk=pk)
    if request.method == 'POST':
        work.title = request.POST.get('title', work.title)
        work.eco_object_id = request.POST.get('object') or None
        work.executor_id = request.POST.get('executor') or None
        work.responsible = request.POST.get('responsible', work.responsible)
        work.amount = request.POST.get('amount') or 0
        work.status = request.POST.get('status', work.status)
        if request.FILES.get('document'):
            if work.document:
                work.document.delete(save=False)
            work.document = request.FILES.get('document')
        work.save()
        return redirect('ecopark:item', pk=pk)

    context = {
        'work': work,
        'objects': EcoObject.objects.filter(is_active=True),
        'executors': EcoExecutor.objects.filter(is_active=True),
    }
    return render(request, 'site/ecopark/ecopark_edit.html', context)


def delete(request, pk):
    if request.method == 'POST':
        work = get_object_or_404(EcoWork, pk=pk)
        if work.document:
            work.document.delete(save=False)
        work.delete()
    return redirect('ecopark:home')


def work_delete_doc(request, pk):
    if request.method == 'POST':
        work = get_object_or_404(EcoWork, pk=pk)
        if work.document:
            work.document.delete(save=True)
    return redirect('ecopark:item', pk=pk)


# ─────────────────────────── Обходы: точки и чек-листы ───────────────────────────

def _rounds_monitor_required(view):
    """
    Доступ к журналу/неисправностям: полный админ (ECOPARK) либо руководитель
    отдела (employee.head) — а не по статичному праву роли, иначе право
    пришлось бы выдавать всей роли целиком и оно утекло бы на рядовых
    сотрудников той же роли. Плюс индивидуальные ALLOW-разрешения (FE-03).
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            response = redirect('account:auth')
            response['Location'] += f"?next={request.path}"
            return response

        from account.role_permissions import RolePermissions, PermissionEnums
        from account.services.permissions import user_has_permission

        employee = getattr(request.user, 'employee_info', None)
        allowed = (
            request.user.is_superuser
            or RolePermissions.checkPermission(request.user.role, PermissionEnums.ECOPARK)
            or (employee is not None and getattr(employee, 'head', False))
            or user_has_permission(request.user, PermissionEnums.ROUNDS_MONITOR)
        )
        if not allowed:
            raise PermissionDenied('Журнал и неисправности обходов')
        return view(request, *args, **kwargs)
    return wrapper


def round_points_list(request):
    points = RoundPoint.objects.select_related('eco_object', 'checklist').order_by('name')
    return render(request, 'site/ecopark/round_points_list.html', {'points': points})


def _parse_geo_field(value):
    """Пусто/мусор в поле широты-долготы — не 500-я, а просто "не задано"."""
    from decimal import Decimal, InvalidOperation
    value = (value or '').strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def round_point_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        location = request.POST.get('location', '').strip()
        eco_object_id = request.POST.get('eco_object') or None
        checklist_id = request.POST.get('checklist') or None
        interval = request.POST.get('check_interval_hours') or 24
        if not name:
            return render(request, 'site/ecopark/round_point_form.html', {
                'title': 'Новая точка обхода',
                'error': 'Название обязательно',
                'form_name': name,
                'form_location': location,
                'objects': EcoObject.objects.filter(is_active=True),
                'checklists': ChecklistTemplate.objects.filter(is_active=True),
            })
        point = RoundPoint.objects.create(
            name=name,
            location=location,
            eco_object_id=eco_object_id,
            checklist_id=checklist_id,
            check_interval_hours=interval,
            latitude=_parse_geo_field(request.POST.get('latitude')),
            longitude=_parse_geo_field(request.POST.get('longitude')),
            created_by=request.user,
        )
        return redirect('ecopark:round_point_edit', pk=point.pk)

    return render(request, 'site/ecopark/round_point_form.html', {
        'title': 'Новая точка обхода',
        'form_name': '',
        'form_location': '',
        'objects': EcoObject.objects.filter(is_active=True),
        'checklists': ChecklistTemplate.objects.filter(is_active=True),
    })


def _save_equipment(request, point):
    ids = request.POST.getlist('equipment_id[]')
    names = request.POST.getlist('equipment_name[]')
    descriptions = request.POST.getlist('equipment_description[]')
    deletes = set(request.POST.getlist('equipment_delete[]'))

    with transaction.atomic():
        for eq_id, name, description in zip(ids, names, descriptions):
            name = name.strip()
            if eq_id and eq_id in deletes:
                Equipment.objects.filter(pk=eq_id, point=point).delete()
                continue
            if not name:
                continue
            if eq_id:
                Equipment.objects.filter(pk=eq_id, point=point).update(
                    name=name, description=description.strip(),
                )
            else:
                Equipment.objects.create(
                    point=point, name=name, description=description.strip(),
                )


def round_point_edit(request, pk):
    point = get_object_or_404(RoundPoint, pk=pk)
    if request.method == 'POST':
        point.name = request.POST.get('name', point.name).strip()
        point.location = request.POST.get('location', point.location).strip()
        point.eco_object_id = request.POST.get('eco_object') or None
        point.checklist_id = request.POST.get('checklist') or None
        point.check_interval_hours = request.POST.get('check_interval_hours') or point.check_interval_hours
        point.latitude = _parse_geo_field(request.POST.get('latitude'))
        point.longitude = _parse_geo_field(request.POST.get('longitude'))
        point.is_active = request.POST.get('is_active') == 'on'
        point.save()
        _save_equipment(request, point)
        return redirect('ecopark:round_points_list')

    return render(request, 'site/ecopark/round_point_form.html', {
        'title': 'Точка обхода',
        'point': point,
        'objects': EcoObject.objects.filter(is_active=True),
        'checklists': ChecklistTemplate.objects.filter(is_active=True),
        'equipment': point.equipment.order_by('name'),
        'scan_url': request.build_absolute_uri(reverse('ecopark:rounds_scan', args=[point.uuid])),
    })


def round_point_delete(request, pk):
    from django.db.models import ProtectedError

    point = get_object_or_404(RoundPoint, pk=pk)
    has_history = point.visits.exists()

    if request.method == 'POST':
        if request.POST.get('action') == 'deactivate':
            point.is_active = False
            point.save(update_fields=['is_active'])
            return redirect('ecopark:round_points_list')
        try:
            point.delete()
        except ProtectedError:
            # По точке уже есть обходы — сохраняем историю, только деактивируем.
            point.is_active = False
            point.save(update_fields=['is_active'])
        return redirect('ecopark:round_points_list')

    return render(request, 'site/ecopark/round_point_confirm_delete.html', {
        'point': point,
        'has_history': has_history,
    })


def _qr_data_uri(text):
    import base64
    import io
    import qrcode

    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def _resolve_pdf_font_path():
    from pathlib import Path
    from django.conf import settings
    candidates = [
        Path(settings.BASE_DIR) / 'static' / 'site' / 'fonts' / 'NotoSans-Regular.ttf',
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def round_point_label(request, pk):
    """PDF-этикетка со статичным QR точки — печатается и клеится на месте.

    Встраивание кириллического шрифта — тот же приём, что в
    finances/services/invoice_pdf.py: xhtml2pdf не резолвит file:// сам,
    поэтому шрифт подсовываем через link_callback.
    """
    from xhtml2pdf import pisa
    from io import BytesIO

    point = get_object_or_404(RoundPoint, pk=pk)
    scan_url = request.build_absolute_uri(reverse('ecopark:rounds_scan', args=[point.uuid]))
    font_path = _resolve_pdf_font_path()
    if not font_path:
        raise Http404('Не найден шрифт для PDF (static/site/fonts/NotoSans-Regular.ttf)')

    html = render_to_string('site/ecopark/pdf/round_point_label.html', {
        'point': point,
        'qr_data_uri': _qr_data_uri(scan_url),
        'pdf_font_family': 'RoundLabelFont',
        'pdf_font_file': font_path.name,
    })

    def _link_callback(uri, rel):
        if uri == font_path.name:
            return str(font_path)
        return uri

    result = BytesIO()
    pdf_status = pisa.CreatePDF(
        html, dest=result, encoding='utf-8',
        link_callback=_link_callback, path=str(font_path.parent),
    )
    if pdf_status.err:
        raise Http404('Не удалось сформировать PDF')

    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="qr-{point.pk}.pdf"'
    return response


# ─────────────────────────── Чек-листы ───────────────────────────

def checklist_templates_list(request):
    templates = ChecklistTemplate.objects.prefetch_related('items').order_by('name')
    return render(request, 'site/ecopark/checklist_templates_list.html', {'templates': templates})


def checklist_template_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            return render(request, 'site/ecopark/checklist_template_form.html', {
                'title': 'Новый чек-лист',
                'error': 'Название обязательно',
                'form_name': name,
            })
        template = ChecklistTemplate.objects.create(name=name, created_by=request.user)
        return redirect('ecopark:checklist_template_edit', pk=template.pk)

    return render(request, 'site/ecopark/checklist_template_form.html', {
        'title': 'Новый чек-лист',
        'form_name': '',
    })


def _save_checklist_items(request, template):
    ids = request.POST.getlist('item_id[]')
    texts = request.POST.getlist('item_text[]')
    deletes = set(request.POST.getlist('item_delete[]'))
    photos = set(request.POST.getlist('item_requires_photo[]'))

    from django.db.models import ProtectedError

    skipped_deletes = []
    with transaction.atomic():
        order = 0
        for idx, (item_id, text) in enumerate(zip(ids, texts)):
            text = text.strip()
            if item_id and item_id in deletes:
                item = ChecklistItem.objects.filter(pk=item_id, template=template).first()
                if item:
                    try:
                        item.delete()
                    except ProtectedError:
                        # По пункту уже есть исторические ответы обходов —
                        # удалить нельзя, иначе пропала бы история. Просто
                        # оставляем пункт как есть (текст могли поменять).
                        skipped_deletes.append(item.text)
                        if text:
                            item.text = text
                            item.order = order
                            item.save(update_fields=['text', 'order'])
                            order += 1
                continue
            if not text:
                continue
            requires_photo = str(idx) in photos or item_id in photos
            if item_id:
                ChecklistItem.objects.filter(pk=item_id, template=template).update(
                    text=text, order=order, requires_photo_on_fail=requires_photo,
                )
            else:
                ChecklistItem.objects.create(
                    template=template, text=text, order=order,
                    requires_photo_on_fail=requires_photo,
                )
            order += 1

    return skipped_deletes


def checklist_template_edit(request, pk):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            template.name = name
        template.is_active = request.POST.get('is_active') == 'on'
        template.save()
        skipped = _save_checklist_items(request, template)
        if skipped:
            from django.contrib import messages
            messages.warning(
                request,
                'Не удалось удалить пункт(ы) «' + '», «'.join(skipped) +
                '» — по ним уже есть отметки в пройденных обходах, история сохранена.',
            )
        return redirect('ecopark:checklist_templates_list')

    return render(request, 'site/ecopark/checklist_template_form.html', {
        'title': 'Чек-лист',
        'template': template,
        'items': template.items.order_by('order', 'id'),
    })


def checklist_template_delete(request, pk):
    from django.db.models import ProtectedError

    template = get_object_or_404(ChecklistTemplate, pk=pk)
    has_history = RoundVisitAnswer.objects.filter(item__template=template).exists()

    if request.method == 'POST':
        if request.POST.get('action') == 'deactivate':
            template.is_active = False
            template.save(update_fields=['is_active'])
            return redirect('ecopark:checklist_templates_list')
        try:
            template.delete()
        except ProtectedError:
            # Хотя бы у одного пункта уже есть отметки в пройденных обходах —
            # каскадное удаление пунктов упёрлось бы в PROTECT. Сохраняем
            # историю, только деактивируем чек-лист.
            template.is_active = False
            template.save(update_fields=['is_active'])
        return redirect('ecopark:checklist_templates_list')

    return render(request, 'site/ecopark/checklist_template_confirm_delete.html', {
        'template': template,
        'has_history': has_history,
    })


# ─────────────────────────── Прохождение обхода (mobile-first) ───────────────────────────

def rounds_scan(request, point_uuid):
    if not request.user.is_authenticated:
        response = redirect('account:auth')
        response['Location'] += f"?next={request.path}"
        return response

    point = RoundPoint.objects.filter(uuid=point_uuid).select_related('checklist').first()
    if point is None:
        return render(request, 'site/ecopark/rounds_scan.html', {
            'error': 'QR-код не распознан — точка не найдена',
        }, status=404)
    if not point.is_active:
        return render(request, 'site/ecopark/rounds_scan.html', {
            'error': 'Эта точка сейчас неактивна',
            'point': point,
        }, status=400)

    employee = getattr(request.user, 'employee_info', None)
    if not employee:
        return render(request, 'site/ecopark/rounds_scan.html', {
            'error': 'Профиль сотрудника не найден',
            'point': point,
        }, status=403)

    items = list(point.checklist.items.order_by('order', 'id')) if point.checklist else []

    if request.method == 'POST':
        errors = []
        answers_payload = []
        for item in items:
            passed = request.POST.get(f'item_{item.pk}_passed') == 'yes'
            comment = request.POST.get(f'item_{item.pk}_comment', '').strip()
            photo = request.FILES.get(f'item_{item.pk}_photo')
            if not passed and item.requires_photo_on_fail and not photo:
                errors.append({'item': item.text, 'msg': 'приложите фото несоответствия'})
            answers_payload.append((item, passed, comment, photo))

        if errors:
            return render(request, 'site/ecopark/rounds_scan.html', {
                'point': point,
                'items': items,
                'errors': errors,
            }, status=400)

        with transaction.atomic():
            visit = RoundVisit.objects.create(
                point=point,
                employee=employee,
                comment=request.POST.get('comment', '').strip(),
                latitude=_parse_geo_field(request.POST.get('latitude')),
                longitude=_parse_geo_field(request.POST.get('longitude')),
            )
            for item, passed, comment, photo in answers_payload:
                answer = RoundVisitAnswer.objects.create(
                    visit=visit, item=item, passed=passed, comment=comment, photo=photo,
                )
                if not passed:
                    Defect.objects.create(
                        visit=visit,
                        answer=answer,
                        point=point,
                        description=comment or item.text,
                        photo=photo,
                        reported_by=employee,
                    )

        return render(request, 'site/ecopark/rounds_scan_done.html', {'point': point, 'visit': visit})

    return render(request, 'site/ecopark/rounds_scan.html', {'point': point, 'items': items})


# ─────────────────────────── Журнал и KPI (руководитель) ───────────────────────────

def _filtered_visits(request):
    visits = RoundVisit.objects.select_related('point', 'employee__user').order_by('-created_at')

    point_filter = request.GET.get('point')
    employee_filter = request.GET.get('employee')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    overdue_only = request.GET.get('overdue') == 'on'

    if point_filter:
        visits = visits.filter(point_id=point_filter)
    if employee_filter:
        visits = visits.filter(employee_id=employee_filter)
    if date_from:
        visits = visits.filter(created_at__date__gte=date_from)
    if date_to:
        visits = visits.filter(created_at__date__lte=date_to)

    all_points = list(RoundPoint.objects.filter(is_active=True))
    overdue_points = [p for p in all_points if p.is_overdue]
    if overdue_only:
        overdue_ids = {p.pk for p in overdue_points}
        visits = visits.filter(point_id__in=overdue_ids)

    return visits, all_points, overdue_points


@_rounds_monitor_required
def rounds_journal(request):
    visits, all_points, overdue_points = _filtered_visits(request)

    today = timezone.localdate()
    week_start = today - timezone.timedelta(days=today.weekday())

    kpi = {
        'today': RoundVisit.objects.filter(created_at__date=today).count(),
        'week': RoundVisit.objects.filter(created_at__date__gte=week_start).count(),
        'overdue_points': len(overdue_points),
        'open_defects': Defect.objects.exclude(status=Defect.STATUS_RESOLVED).count(),
        'total_points': len(all_points),
    }

    return render(request, 'site/ecopark/rounds_journal.html', {
        'visits': visits[:200],
        'kpi': kpi,
        'points': all_points,
        'overdue_points': overdue_points,
    })


@_rounds_monitor_required
def rounds_journal_export(request):
    import openpyxl

    visits, _all_points, _overdue_points = _filtered_visits(request)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Журнал обходов'
    ws.append(['Точка', 'Сотрудник', 'Когда', 'Результат', 'Геолокация', 'Комментарий'])

    geo_labels = {
        RoundVisit.GEO_OK: 'Рядом с точкой',
        RoundVisit.GEO_MISMATCH: 'Не рядом с точкой',
        RoundVisit.GEO_MISSING: 'Нет данных',
        RoundVisit.GEO_UNKNOWN: '—',
    }

    for visit in visits.select_related('point', 'employee__user')[:5000]:
        ws.append([
            visit.point.name,
            visit.employee.user.get_full_name() or visit.employee.user.username,
            timezone.localtime(visit.created_at).strftime('%d.%m.%Y %H:%M'),
            'Есть несоответствия' if visit.has_failed_items else 'Всё в порядке',
            geo_labels.get(visit.geo_status, '—'),
            visit.comment,
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="rounds_journal.xlsx"'
    wb.save(response)
    return response


@_rounds_monitor_required
def defects_list(request):
    defects = Defect.objects.select_related('point', 'reported_by__user', 'resolved_by').order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        defects = defects.filter(status=status_filter)

    return render(request, 'site/ecopark/defects_list.html', {
        'defects': defects,
        'status_choices': Defect.STATUS_CHOICES,
    })


@_rounds_monitor_required
def defect_resolve(request, pk):
    defect = get_object_or_404(Defect, pk=pk)
    if request.method == 'POST':
        defect.status = Defect.STATUS_RESOLVED
        defect.resolved_by = request.user
        defect.resolved_at = timezone.now()
        defect.save()
    return redirect('ecopark:defects_list')


@_rounds_monitor_required
def defect_escalate(request, pk):
    defect = get_object_or_404(Defect, pk=pk)
    if request.method == 'POST':
        defect.priority = Defect.PRIORITY_CRITICAL
        defect.assigned_to = request.user
        defect.escalated_at = timezone.now()
        if defect.status == Defect.STATUS_OPEN:
            defect.status = Defect.STATUS_IN_PROGRESS
        defect.save()
    return redirect('ecopark:defects_list')
