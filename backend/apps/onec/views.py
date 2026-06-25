import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.generic import ListView, View
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.db import models
from django.db import transaction
from django.utils import timezone
from addits.models import Comment

from account.role_permissions import login_required
from account.services.access_scope import (
    filter_counterparties_queryset,
    get_visible_counterparties,
    user_can_view_counterparty,
)
from .models import Counterparty, Invoice, InvoiceItem
from .client_1c.client import Client1C
from .forms import CounterpartyForm
from .services.seed_counterparties import seed_demo_counterparties
from .services.sync_counterparties import sync_counterparties_from_1c

from rest_framework import viewsets, filters
from .serializers import CounterpartySerializer, InvoiceSerializer

logger = logging.getLogger(__name__)

def get_1c_client():
    return Client1C(
        base_url=settings.ONE_C_BASE_URL,            
        basic_auth_user=settings.ONE_C_BASIC_AUTH_USER,
        basic_auth_password=settings.ONE_C_BASIC_AUTH_PASSWORD,
        api_user=settings.ONE_C_API_USER,
        api_password=settings.ONE_C_API_PASSWORD
    )

@method_decorator(login_required, name='dispatch')
class CounterpartyListView(ListView):
    model = Counterparty
    template_name = 'site/onec/counterparty_list.html'
    context_object_name = 'counterparties'
    paginate_by = 50

    def get_queryset(self):
        queryset = filter_counterparties_queryset(
            super().get_queryset().select_related('counterparty_type', 'counterparty_type__access_scope'),
            self.request.user,
        )

        search_query = self.request.GET.get('search')

        if search_query:
            queryset = queryset.filter(
                models.Q(short_name__icontains=search_query)
                | models.Q(full_name__icontains=search_query)
                | models.Q(bin_number__icontains=search_query)
                | models.Q(phone__icontains=search_query)
            )

        type_id = self.request.GET.get('type')
        if type_id:
            queryset = queryset.filter(counterparty_type_id=type_id)

        return queryset

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET' and not Counterparty.objects.exists():
            seed_demo_counterparties(force=False)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible = get_visible_counterparties(self.request.user)
        context['total_count'] = visible.count()
        context['onec_configured'] = bool(getattr(settings, 'ONE_C_BASE_URL', None))
        from .models import CounterpartyType
        context['counterparty_types'] = CounterpartyType.objects.filter(is_active=True)
        context['f_type'] = self.request.GET.get('type', '')
        from account.services.access_scope import user_can_manage_access_scopes
        context['can_manage_acl'] = user_can_manage_access_scopes(self.request.user)
        return context


@login_required
def counterparty_sync(request):
    if request.method != 'POST':
        return redirect('onec:counterparty_list')

    result = sync_counterparties_from_1c()
    status = result.get('status')

    if status == 'skipped':
        messages.warning(request, '1С не настроена. Заполните ONE_C_* в .env или загрузите демо-контрагентов.')
    elif status == 'error':
        messages.error(request, f'Ошибка синхронизации: {result.get("error", "неизвестная ошибка")}')
    elif status == 'ok':
        created = result.get('created', 0)
        updated = result.get('updated', 0)
        if created == 0 and updated == 0:
            messages.info(request, 'Синхронизация завершена: новых данных из 1С нет.')
        else:
            messages.success(
                request,
                f'Контрагенты из 1С: добавлено {created}, обновлено {updated}.',
            )
    return redirect('onec:counterparty_list')


@login_required
def counterparty_seed_demo(request):
    if request.method != 'POST':
        return redirect('onec:counterparty_list')

    force = request.POST.get('force') == '1'
    result = seed_demo_counterparties(force=force)
    if result.get('status') == 'skipped':
        messages.info(
            request,
            f'В базе уже {result.get("count", 0)} контрагентов. '
            'Отметьте «перезаписать демо» или добавьте вручную.',
        )
    else:
        messages.success(
            request,
            f'Демо-контрагенты загружены: создано {result.get("created", 0)}, '
            f'обновлено {result.get("updated", 0)} (всего {result.get("total", 0)}).',
        )
    return redirect('onec:counterparty_list')


@login_required
def counterparty_create(request):
    form = CounterpartyForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        counterparty = form.save(commit=False)
        counterparty.synced_at = timezone.now()
        counterparty.save()
        messages.success(request, f'Контрагент «{counterparty.short_name}» добавлен.')
        return redirect('onec:counterparty_detail', pk=counterparty.pk)

    return render(request, 'site/onec/counterparty_form.html', {
        'form': form,
        'title': 'Новый контрагент',
        'is_edit': False,
    })


@login_required
def counterparty_edit(request, pk):
    counterparty = get_object_or_404(Counterparty, pk=pk)
    if not user_can_view_counterparty(request.user, counterparty):
        raise Http404
    form = CounterpartyForm(request.POST or None, instance=counterparty)

    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        updated.synced_at = timezone.now()
        updated.save()
        messages.success(request, 'Контрагент сохранён.')
        return redirect('onec:counterparty_detail', pk=updated.pk)

    return render(request, 'site/onec/counterparty_form.html', {
        'form': form,
        'counterparty': counterparty,
        'title': 'Редактирование контрагента',
        'is_edit': True,
    })


@login_required
def counterparty_detail(request, pk):
    counterparty = get_object_or_404(
        filter_counterparties_queryset(
            Counterparty.objects.select_related('counterparty_type', 'counterparty_type__access_scope'),
            request.user,
        ),
        pk=pk,
    )
    comments = Comment.objects.filter(
        target_type='counterparty', target_id=counterparty.pk
    ).select_related('user').order_by('id')

    return render(request, 'site/onec/counterparty_detail.html', {
        'counterparty': counterparty,
        'tasks_count': counterparty.tasks.count(),
        'invoices_count': counterparty.invoices.count(),
        'comments': comments,
    })


@login_required
def counterparty_delete(request, pk):
    counterparty = get_object_or_404(Counterparty, pk=pk)
    if not user_can_view_counterparty(request.user, counterparty):
        raise Http404

    if request.method != 'POST':
        return redirect('onec:counterparty_detail', pk=pk)

    name = counterparty.short_name or counterparty.full_name
    try:
        counterparty.delete()
    except models.ProtectedError:
        messages.error(
            request,
            f'Нельзя удалить «{name}»: с контрагентом связаны счета или операции.',
        )
        return redirect('onec:counterparty_detail', pk=pk)

    messages.success(request, f'Контрагент «{name}» удалён.')
    return redirect('onec:counterparty_list')


@login_required
def counterparty_search_api(request):
    q = request.GET.get('q', '')
    counterparties = filter_counterparties_queryset(
        Counterparty.objects.all(),
        request.user,
    ).filter(
        models.Q(short_name__icontains=q) | models.Q(bin_number__icontains=q)
    )[:20]
    results = [
        {'id': cp.id, 'text': f"{cp.short_name} (БИН: {cp.bin_number or '---'})"} 
        for cp in counterparties
    ]
    return JsonResponse({'results': results})

@method_decorator(login_required, name='dispatch')
class InvoiceCreateView(View):
    def get(self, request):
        return render(request, 'site/onec/invoice_form.html')

    def post(self, request):
        cp_id = request.POST.get('counterparty')
        comment = request.POST.get('comment')
        
        names = request.POST.getlist('item_name[]')
        qtys = request.POST.getlist('item_qty[]')
        prices = request.POST.getlist('item_price[]')

        if not cp_id or not names:
            messages.error(request, "Ошибка: выберите контрагента и добавьте товары.")
            return redirect('onec:invoice_create')

        try:
            with transaction.atomic():
                counterparty = get_object_or_404(
                    filter_counterparties_queryset(Counterparty.objects.all(), request.user),
                    id=cp_id,
                )
                
                invoice = Invoice.objects.create(
                    counterparty=counterparty,
                    comment=comment,
                    status='created'
                )

                total_sum = 0
                for i in range(len(names)):
                    if not names[i].strip():
                        continue
                        
                    qty = float(qtys[i]) if qtys[i] else 0
                    price = float(prices[i]) if prices[i] else 0
                    
                    item = InvoiceItem.objects.create(
                        invoice=invoice,
                        name=names[i],
                        quantity=qty,
                        price=price
                    )
                    total_sum += item.total

                invoice.Sum = total_sum
                invoice.save()

            try:
                client = get_1c_client()
                client.authenticate()
                
                client.confirm(
                    received_ids=[str(invoice.id)], 
                    status="sent",
                    sync_token=f"web_creation_{invoice.id}"
                )

                invoice.status = 'sent'
                invoice.save()
                messages.success(request, f"Счет №{invoice.id} успешно создан и отправлен в 1С.")
                
            except Exception as e_1c:
                logger.error(f"1C Integration Error: {e_1c}")
                messages.warning(request, f"Счет сохранен в системе, но не отправлен в 1С: {e_1c}")

            return redirect('onec:counterparty_list')

        except Exception as e:
            logger.error(f"Database Error: {e}")
            messages.error(request, f"Произошла ошибка при сохранении: {e}")
            return redirect('onec:invoice_create')


class CounterpartyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CounterpartySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['short_name', 'bin_number']

    def get_queryset(self):
        return filter_counterparties_queryset(
            Counterparty.objects.select_related('counterparty_type'),
            self.request.user,
        )

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-Date')
    serializer_class = InvoiceSerializer