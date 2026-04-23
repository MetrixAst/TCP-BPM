import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.db import models
from django.db import transaction

from .models import Counterparty, Invoice, InvoiceItem
from .client_1c.client import Client1C

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

class CounterpartyListView(ListView):
    model = Counterparty
    template_name = 'site/onec/counterparty_list.html'
    context_object_name = 'counterparties'
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset()
        
        search_query = self.request.GET.get('search')
        
        if search_query:
            queryset = queryset.filter(
                models.Q(short_name__icontains=search_query) | 
                models.Q(bin_number__icontains=search_query)
            )
            
        return queryset

class CounterpartyDetailView(DetailView):
    model = Counterparty
    template_name = 'site/onec/counterparty_detail.html'
    context_object_name = 'counterparty'

def counterparty_search_api(request):
    q = request.GET.get('q', '')
    counterparties = Counterparty.objects.filter(
        models.Q(short_name__icontains=q) | models.Q(bin_number__icontains=q)
    )[:20]
    results = [
        {'id': cp.id, 'text': f"{cp.short_name} (БИН: {cp.bin_number or '---'})"} 
        for cp in counterparties
    ]
    return JsonResponse({'results': results})

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
                counterparty = get_object_or_404(Counterparty, id=cp_id)
                
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
    queryset = Counterparty.objects.all()
    serializer_class = CounterpartySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['short_name', 'bin_number']

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-Date')
    serializer_class = InvoiceSerializer