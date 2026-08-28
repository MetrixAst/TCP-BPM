import json
import os
from django.http import Http404, JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from documents import onlyoffice
from django.shortcuts import redirect, render, get_object_or_404
import secrets
from django.utils import timezone
from .models import (
    InspectionPoint, Equipment, ChecklistItem,
    InspectionSchedule, InspectionRound, InspectionResult, Defect, 
    EcoObject, EcoExecutor, EcoWork
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


def inspection_points(request):
    points = InspectionPoint.objects.select_related('eco_object').order_by('name')
    return render(request, 'site/ecopark/inspection/points_list.html', {
        'points': points,
    })


def inspection_point_create(request):
    from ecopark.models import EcoObject
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        point_type = request.POST.get('point_type', 'other')
        location = request.POST.get('location', '').strip()
        eco_object_id = request.POST.get('eco_object')
        interval_hours = int(request.POST.get('interval_hours', 4))

        point = InspectionPoint.objects.create(
            name=name,
            point_type=point_type,
            location=location,
            eco_object_id=eco_object_id or None,
        )

        InspectionSchedule.objects.create(
            point=point,
            interval_hours=interval_hours,
            assigned_to=request.user,
        )

        checklist_items = request.POST.getlist('checklist_items')
        for i, item_text in enumerate(checklist_items):
            if item_text.strip():
                ChecklistItem.objects.create(
                    point=point,
                    order=i,
                    text=item_text.strip(),
                )

        return redirect('ecopark:inspection_points')

    eco_objects = EcoObject.objects.filter(is_active=True)
    return render(request, 'site/ecopark/inspection/point_form.html', {
        'eco_objects': eco_objects,
        'point_types': InspectionPoint.TYPE_CHOICES,
    })


def inspection_point_edit(request, pk):
    point = get_object_or_404(InspectionPoint, pk=pk)
    if request.method == 'POST':
        point.name = request.POST.get('name', point.name).strip()
        point.point_type = request.POST.get('point_type', point.point_type)
        point.location = request.POST.get('location', point.location).strip()
        point.is_active = request.POST.get('is_active') == 'on'
        point.save()
        return redirect('ecopark:inspection_points')

    from ecopark.models import EcoObject
    return render(request, 'site/ecopark/inspection/point_form.html', {
        'point': point,
        'eco_objects': EcoObject.objects.filter(is_active=True),
        'point_types': InspectionPoint.TYPE_CHOICES,
        'checklist_items': point.checklist_items.filter(is_active=True),
        'schedule': point.schedules.filter(is_active=True).first(),
    })


def inspection_point_delete(request, pk):
    point = get_object_or_404(InspectionPoint, pk=pk)
    if request.method == 'POST':
        point.is_active = False
        point.save()
        return redirect('ecopark:inspection_points')
    return render(request, 'site/ecopark/inspection/point_confirm_delete.html', {'point': point})


def inspection_point_qr(request, pk):
    point = get_object_or_404(InspectionPoint, pk=pk, is_active=True)
    scan_url = request.build_absolute_uri(f'/ecopark/inspection/scan/{point.qr_code}/')
    return render(request, 'site/ecopark/inspection/point_qr.html', {
        'point': point,
        'scan_url': scan_url,
    })


def inspection_scan(request, qr_code):
    point = get_object_or_404(InspectionPoint, qr_code=qr_code, is_active=True)
    if not request.user.is_authenticated:
        return redirect(f'/account/auth?next=/ecopark/inspection/scan/{qr_code}/')
    checklist_items = point.checklist_items.filter(is_active=True).order_by('order')
    return render(request, 'site/ecopark/inspection/scan_form.html', {
        'point': point,
        'checklist_items': checklist_items,
    })


def inspection_submit(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не разрешён'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Требуется авторизация'}, status=403)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    point_id = data.get('point_id')
    results = data.get('results', [])
    notes = data.get('notes', '')
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

    point = get_object_or_404(InspectionPoint, pk=point_id, is_active=True)

    round_obj = InspectionRound.objects.create(
        point=point,
        employee=request.user,
        status=InspectionRound.STATUS_COMPLETED,
        notes=notes,
        ip_address=ip,
    )

    has_defects = False
    for result_data in results:
        item_id = result_data.get('checklist_item_id')
        status = result_data.get('status', InspectionResult.STATUS_OK)
        result_notes = result_data.get('notes', '')

        try:
            checklist_item = ChecklistItem.objects.get(pk=item_id, point=point)
        except ChecklistItem.DoesNotExist:
            continue

        result = InspectionResult.objects.create(
            round=round_obj,
            checklist_item=checklist_item,
            status=status,
            notes=result_notes,
        )

        if status == InspectionResult.STATUS_DEFECT:
            has_defects = True
            Defect.objects.create(
                result=result,
                description=result_notes or f'Неисправность: {checklist_item.text}',
                priority=Defect.PRIORITY_HIGH,
            )

    return JsonResponse({
        'success': True,
        'round_id': round_obj.pk,
        'has_defects': has_defects,
        'message': 'Обход успешно завершён',
    }, json_dumps_params={'ensure_ascii': False})


def inspection_round_detail(request, pk):
    round_obj = get_object_or_404(InspectionRound, pk=pk)
    results = round_obj.results.select_related('checklist_item').all()
    return render(request, 'site/ecopark/inspection/round_detail.html', {
        'round': round_obj,
        'results': results,
    })


def inspection_journal(request):
    rounds = InspectionRound.objects.select_related(
        'point', 'employee'
    ).order_by('-server_time')

    # Фильтры
    point_id = request.GET.get('point')
    employee_id = request.GET.get('employee')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if point_id:
        rounds = rounds.filter(point_id=point_id)
    if employee_id:
        rounds = rounds.filter(employee_id=employee_id)
    if date_from:
        rounds = rounds.filter(server_time__date__gte=date_from)
    if date_to:
        rounds = rounds.filter(server_time__date__lte=date_to)

    return render(request, 'site/ecopark/inspection/journal.html', {
        'rounds': rounds[:100],
        'points': InspectionPoint.objects.filter(is_active=True),
    })


def inspection_report(request):
    from django.db.models import Count, Q
    points = InspectionPoint.objects.filter(is_active=True).annotate(
        total_rounds=Count('rounds'),
        completed_rounds=Count('rounds', filter=Q(rounds__status='completed')),
        open_defects=Count('rounds__results__defect', filter=Q(rounds__results__defect__status='open')),
    )
    return render(request, 'site/ecopark/inspection/report.html', {
        'points': points,
    })


def inspection_export(request):
    import openpyxl
    from django.http import HttpResponse

    rounds = InspectionRound.objects.select_related('point', 'employee').order_by('-server_time')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Журнал обходов'
    ws.append(['Точка', 'Сотрудник', 'Статус', 'Время', 'Примечания', 'Неисправности'])

    for r in rounds:
        defects_count = Defect.objects.filter(
            result__round=r, status=Defect.STATUS_OPEN
        ).count()
        ws.append([
            r.point.name,
            r.employee.get_name if r.employee else '—',
            r.get_status_display(),
            r.server_time.strftime('%d.%m.%Y %H:%M'),
            r.notes,
            defects_count,
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="inspection_journal.xlsx"'
    wb.save(response)
    return response


def defect_escalate(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не разрешён'}, status=405)
    defect = get_object_or_404(Defect, pk=pk)
    defect.priority = Defect.PRIORITY_CRITICAL
    defect.escalated_at = timezone.now()
    defect.status = Defect.STATUS_IN_PROGRESS
    defect.save(update_fields=['priority', 'escalated_at', 'status'])
    return JsonResponse({'success': True, 'message': 'Неисправность передана на срочное устранение'}, json_dumps_params={'ensure_ascii': False})