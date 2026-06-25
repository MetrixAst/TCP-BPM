import json
import os
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from documents import onlyoffice
from django.shortcuts import redirect, render, get_object_or_404
from .models import EcoObject, EcoExecutor, EcoWork


def _fmt_amount(value):
    return f'{int(value):,}'.replace(',', ' ')


def home(request):
    works = EcoWork.objects.select_related('eco_object', 'executor').all()

    obj_filter = request.GET.get('object')
    exec_filter = request.GET.get('executor')
    status_filter = request.GET.get('status')

    if obj_filter:
        works = works.filter(eco_object_id=obj_filter)
    if exec_filter:
        works = works.filter(executor_id=exec_filter)
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