from django.shortcuts import redirect, render, get_object_or_404
from account.role_permissions import need_permission, PermissionEnums, login_required as _login_required
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.contrib import messages
from decimal import Decimal
from django import forms as django_forms

from project.utils import get_or_none

from .forms import FinanceItemForm, GeneratedInvoiceForm, GeneratedInvoiceItemFormSet
from .models import (
    FinanceItem, TenantPaymentRegistry, PaymentCalendarEntry, GeneratedInvoice,
    BudgetCategory, BudgetItem, FinancialStatement, CashFlowRecord, CreditModel,
)
from .serializers import FinanceItemSerializer

from datetime import date
from django.db.models import Q
from django.utils import timezone

from account.role_permissions import RoleEnums


def _finance_filter_context(extra=None):
    """Арендаторы для глобального фильтра на фин. страницах."""
    from tenants.models import Tenant

    ctx = {'finance_filter_tenants': Tenant.objects.order_by('name')}
    if extra:
        ctx.update(extra)
    return ctx


@need_permission(PermissionEnums.FINANCES)
def calendar(request):
    return redirect('finances:payment_calendar')


@need_permission(PermissionEnums.FINANCES)
def calendar_action(request, action):

    if action == 'json':
        qs = FinanceItem.objects.all()
        res = FinanceItemSerializer(qs, many=True)

        return JsonResponse(res.data, safe=False)

    if request.method == 'POST':
        pk = request.POST.get('id', None)
        instance = None
        if pk is not None:
            instance = get_or_none(FinanceItem, pk=pk)

        if action == 'delete':
            instance.delete()

            return JsonResponse({})
        else:
            form = FinanceItemForm(request.POST, instance=instance)
            if form.is_valid():
                new = form.save(commit=False)
                new.user = request.user
                new.save()

                res = FinanceItemSerializer(new)

                return JsonResponse(res.data)

    return JsonResponse({}, status=400)


def budget(request, pk):
    context = {

    }

    return render(request, 'site/finances/budget/budget.html', context)


def budget_create(request):
    return redirect('finances:budget_list')


@need_permission(PermissionEnums.FINANCES)
def bill(request):
    """Счета компании (банковские) — данные из 1С пока не подключены."""
    return render(request, 'site/finances/bill.html', {
        'has_data': False,
    })


@need_permission(PermissionEnums.FINANCE_REGISTERS)
def payment_reg(request):
    qs = TenantPaymentRegistry.objects.select_related(
        'tenant', 'tenant__category', 'tenant__room'
    ).order_by('-period', 'tenant__name')

    search      = request.GET.get('search', '').strip()
    status      = request.GET.get('status', '')
    period_from = request.GET.get('period_from', '')
    period_to   = request.GET.get('period_to', '')
    tenant_id   = request.GET.get('tenant', '')

    if search:
        qs = qs.filter(
            Q(tenant__name__icontains=search) |
            Q(contract_number__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if period_from:
        try:
            qs = qs.filter(period__gte=period_from)
        except Exception:
            pass
    if period_to:
        try:
            qs = qs.filter(period__lte=period_to)
        except Exception:
            pass

    STATUS_COLORS = {
        TenantPaymentRegistry.Status.PAID: 'success',
        TenantPaymentRegistry.Status.PARTIAL: 'warning',
        TenantPaymentRegistry.Status.PENDING: 'info',
        TenantPaymentRegistry.Status.OVERDUE: 'danger',
        TenantPaymentRegistry.Status.CANCELLED: 'secondary',
    }

    entries = []
    for entry in qs:
        entries.append({
            'obj':   entry,
            'color': STATUS_COLORS.get(entry.status, 'secondary'),
        })

    from tenants.models import Tenant
    tenants  = Tenant.objects.order_by('name')
    statuses = TenantPaymentRegistry.Status.choices

    context = _finance_filter_context({
        'entries': entries,
        'tenants': tenants,
        'statuses': statuses,
        'today': date.today(),
        'f_search': search,
        'f_status': status,
        'f_tenant': tenant_id,
        'f_period_from': period_from,
        'f_period_to': period_to,
    })

    if request.GET.get('export') == 'xlsx':
        from .services.excel import export_payment_registry
        return export_payment_registry(qs)

    return render(request, 'site/finances/payment_register.html', context)

@need_permission(PermissionEnums.FINANCE_REGISTERS)
def payment_calendar(request):
    from datetime import date, timedelta
    from calendar import monthrange
    from .models import PaymentCalendarEntry
    from tenants.models import Tenant

    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    tenant_id = request.GET.get('tenant', '')
    status    = request.GET.get('status', '')

    qs = PaymentCalendarEntry.objects.select_related(
        'tenant', 'tenant__room'
    ).filter(
        expected_date__year=year,
        expected_date__month=month,
    ).order_by('expected_date', 'tenant__name')

    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if status:
        qs = qs.filter(status=status)

    days_in_month = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    calendar_leading_blanks = month_start.weekday()
    calendar_days = []

    for day in range(1, days_in_month + 1):
        day_date    = date(year, month, day)
        day_entries = [e for e in qs if e.expected_date == day_date]

        planned = sum(e.expected_amount for e in day_entries)
        actual  = sum(e.actual_amount   for e in day_entries)

        calendar_days.append({
            'date':       day_date,
            'entries':    day_entries,
            'count':      len(day_entries),
            'planned':    planned,
            'actual':     actual,
            'is_today':   day_date == today,
            'is_weekend': day_date.weekday() >= 5,
            'has_overdue': any(e.status == 'overdue' for e in day_entries),
        })

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        'calendar_days': calendar_days,
        'calendar_leading_blanks': range(calendar_leading_blanks),
        'tenants':       Tenant.objects.order_by('name'),
        'statuses':      PaymentCalendarEntry.Status.choices,
        'year':          year,
        'month':         month,
        'month_name':    _month_name(month),
        'prev_year':     prev_year,
        'prev_month':    prev_month,
        'next_year':     next_year,
        'next_month':    next_month,
        'today':         today,
        'f_tenant':      tenant_id,
        'f_status':      status,
    }

    return render(request, 'site/finances/payment_calendar.html', context)


@need_permission(PermissionEnums.FINANCE_REGISTERS)
def payment_calendar_day(request, year, month, day):
    from datetime import date
    from .models import PaymentCalendarEntry

    try:
        day_date = date(year, month, day)
    except ValueError:
        from django.http import Http404
        raise Http404

    from django.db.models import Q

    entries = PaymentCalendarEntry.objects.select_related(
        'tenant', 'tenant__room'
    ).filter(
        Q(expected_date=day_date) | Q(actual_date=day_date)
    ).order_by('tenant__name')

    STATUS_COLORS = {
        PaymentCalendarEntry.Status.PLAN:    'info',
        PaymentCalendarEntry.Status.FACT:    'success',
        PaymentCalendarEntry.Status.OVERDUE: 'danger',
    }

    rows = [
        {'obj': e, 'color': STATUS_COLORS.get(e.status, 'secondary')}
        for e in entries
    ]

    total_planned = sum(e.expected_amount for e in entries)
    total_actual  = sum(e.actual_amount   for e in entries)

    context = {
        'day_date':     day_date,
        'rows':         rows,
        'total_planned': total_planned,
        'total_actual':  total_actual,
        'diff':          total_actual - total_planned,
    }

    return render(request, 'site/finances/payment_calendar_day.html', context)


def _month_name(month):
    names = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель',
        'Май', 'Июнь', 'Июль', 'Август',
        'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ]
    return names[month]


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_list(request):
    qs = GeneratedInvoice.objects.select_related(
        'tenant', 'counterparty'
    ).order_by('-created_at')

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '')

    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(number__icontains=search) |
            Q(tenant__name__icontains=search) |
            Q(counterparty__short_name__icontains=search) |
            Q(contract_number__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)

    STATUS_COLORS = {
        GeneratedInvoice.Status.CREATED: 'secondary',
        GeneratedInvoice.Status.SENT: 'info',
        GeneratedInvoice.Status.VIEWED: 'warning',
        GeneratedInvoice.Status.PAID: 'success',
        GeneratedInvoice.Status.CANCELLED: 'danger',
    }

    entries = [
        {'obj': inv, 'color': STATUS_COLORS.get(inv.status, 'secondary')}
        for inv in qs
    ]

    context = {
        'entries':   entries,
        'statuses':  GeneratedInvoice.Status.choices,
        'f_search':  search,
        'f_status':  status,
    }
    return render(request, 'site/finances/invoice_list.html', context)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_create(request):
    form     = GeneratedInvoiceForm(request.POST or None)
    formset  = GeneratedInvoiceItemFormSet(request.POST or None)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        invoice = form.save(commit=False)
        invoice.status = GeneratedInvoice.Status.CREATED
        invoice.save()
        formset.instance = invoice
        formset.save()
        items = invoice.items.all()
        invoice.total_amount = sum(i.total for i in items)
        invoice.vat_amount   = sum(i.vat_amount for i in items)
        invoice.save()
        messages.success(request, f'Счёт №{invoice.number} создан.')
        return redirect('finances:invoice_list')

    context = {'form': form, 'formset': formset, 'title': 'Создать счёт'}
    return render(request, 'site/finances/invoice_form.html', context)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_edit(request, pk):
    invoice = get_object_or_404(GeneratedInvoice, pk=pk)

    if invoice.status == GeneratedInvoice.Status.PAID:
        messages.error(request, 'Оплаченный счёт нельзя редактировать.')
        return redirect('finances:invoice_list')

    form    = GeneratedInvoiceForm(request.POST or None, instance=invoice)
    formset = GeneratedInvoiceItemFormSet(request.POST or None, instance=invoice)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        invoice = form.save()
        formset.save()
        items = invoice.items.all()
        invoice.total_amount = sum(i.total for i in items)
        invoice.vat_amount   = sum(i.vat_amount for i in items)
        invoice.save()
        messages.success(request, f'Счёт №{invoice.number} обновлён.')
        return redirect('finances:invoice_list')

    context = {'form': form, 'formset': formset, 'title': 'Редактировать счёт', 'invoice': invoice}
    return render(request, 'site/finances/invoice_form.html', context)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        GeneratedInvoice.objects.select_related('tenant', 'counterparty').prefetch_related('items'),
        pk=pk,
    )
    STATUS_COLORS = {
        GeneratedInvoice.Status.CREATED: 'secondary',
        GeneratedInvoice.Status.SENT: 'info',
        GeneratedInvoice.Status.VIEWED: 'warning',
        GeneratedInvoice.Status.PAID: 'success',
        GeneratedInvoice.Status.CANCELLED: 'danger',
    }
    context = {
        'invoice': invoice,
        'color':   STATUS_COLORS.get(invoice.status, 'secondary'),
    }
    return render(request, 'site/finances/invoice_detail.html', context)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_pdf(request, pk):
    """PDF счёта: ?inline=1 — preview в браузере, иначе скачивание."""
    invoice = get_object_or_404(
        GeneratedInvoice.objects.select_related('tenant', 'counterparty').prefetch_related('items'),
        pk=pk,
    )
    from .services.invoice_pdf import build_invoice_pdf

    try:
        pdf_bytes = build_invoice_pdf(invoice)
    except Exception:
        return HttpResponse('Ошибка генерации PDF', status=500, content_type='text/plain; charset=utf-8')

    safe_number = ''.join(
        c if c.isascii() and (c.isalnum() or c in '-_') else '_'
        for c in str(invoice.number)
    ).strip('_') or str(invoice.pk)
    filename = f'invoice_{safe_number}.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    disposition = 'inline' if inline else 'attachment'

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Cache-Control'] = 'private, max-age=300'
    return response


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_delete(request, pk):
    invoice = get_object_or_404(GeneratedInvoice, pk=pk)

    if invoice.status == GeneratedInvoice.Status.PAID:
        messages.error(request, 'Оплаченный счёт нельзя удалить.')
        return redirect('finances:invoice_list')

    if request.method == 'POST':
        invoice.delete()
        messages.success(request, 'Счёт удалён.')
    return redirect('finances:invoice_list')


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_send(request, pk):
    invoice = get_object_or_404(GeneratedInvoice, pk=pk)
    if request.method == 'POST' and invoice.status == GeneratedInvoice.Status.CREATED:
        sent_via = request.POST.get('sent_via', GeneratedInvoice.SentVia.EMAIL)

        from finances.services.notifications import (
            send_invoice_via_email,
            send_invoice_via_messenger,
        )

        if sent_via == GeneratedInvoice.SentVia.EMAIL:
            ok = send_invoice_via_email(invoice)
            if ok:
                messages.success(request, f'Счёт №{invoice.number} отправлен по email.')
                try:
                    from onec.services.sync_invoices import notify_onec_invoice_sent
                    notify_onec_invoice_sent(invoice)
                except Exception:
                    pass
            else:
                # email не ушёл (нет получателя / ошибка), но статус всё равно обновляем вручную
                invoice.status   = GeneratedInvoice.Status.SENT
                invoice.sent_via = sent_via
                invoice.sent_at  = timezone.now()
                invoice.save()
                messages.warning(request, f'Счёт №{invoice.number} отмечен как отправленный, но письмо не доставлено.')
        elif sent_via in (GeneratedInvoice.SentVia.WHATSAPP, GeneratedInvoice.SentVia.TELEGRAM):
            send_invoice_via_messenger(invoice, sent_via)
            messages.success(request, f'Счёт №{invoice.number} отправлен через {invoice.get_sent_via_display()}.')
        else:
            # manual
            invoice.status   = GeneratedInvoice.Status.SENT
            invoice.sent_via = sent_via
            invoice.sent_at  = timezone.now()
            invoice.save()
            messages.success(request, f'Счёт №{invoice.number} отмечен как отправленный вручную.')

        try:
            from onec.services.sync_invoices import notify_onec_invoice_sent
            if invoice.status == GeneratedInvoice.Status.SENT:
                notify_onec_invoice_sent(invoice)
        except Exception:
            pass

    return redirect('finances:invoice_detail', pk=pk)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_mark_viewed(request, pk):
    invoice = get_object_or_404(GeneratedInvoice, pk=pk)
    if request.method == 'POST' and invoice.status == GeneratedInvoice.Status.SENT:
        invoice.status = GeneratedInvoice.Status.VIEWED
        invoice.save()
        messages.success(request, f'Счёт №{invoice.number} просмотрен.')
    return redirect('finances:invoice_detail', pk=pk)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_mark_paid(request, pk):
    invoice = get_object_or_404(GeneratedInvoice, pk=pk)
    if request.method == 'POST' and invoice.status in [
        GeneratedInvoice.Status.SENT,
        GeneratedInvoice.Status.VIEWED,
    ]:
        from .services.invoice_registry import apply_invoice_payment_to_registry

        invoice.status = GeneratedInvoice.Status.PAID
        invoice.save(update_fields=['status', 'updated_at'])

        registry = apply_invoice_payment_to_registry(invoice)
        if registry:
            messages.success(
                request,
                f'Счёт №{invoice.number} оплачен. Реестр обновлён '
                f'({registry.tenant}, {registry.period.strftime("%m.%Y")}).',
            )
        elif not invoice.tenant_id:
            messages.warning(
                request,
                f'Счёт №{invoice.number} оплачен, но арендатор не указан — '
                'реестр платежей не обновлён.',
            )
        else:
            messages.success(request, f'Счёт №{invoice.number} оплачен.')
    return redirect('finances:invoice_detail', pk=pk)


@need_permission(PermissionEnums.FINANCE_INVOICES)
def invoice_cancel(request, pk):
    invoice = get_object_or_404(GeneratedInvoice, pk=pk)
    if request.method == 'POST' and invoice.status != GeneratedInvoice.Status.PAID:
        invoice.status = GeneratedInvoice.Status.CANCELLED
        invoice.save()
        messages.success(request, f'Счёт №{invoice.number} отменён.')
    return redirect('finances:invoice_detail', pk=pk)

def _get_budget_access(user):
    if not user.is_authenticated:
        return False, False
    
    role = user.role.value if hasattr(user.role, 'value') else user.role

    can_edit = role in [
        RoleEnums.CFO.value,
        RoleEnums.ADMINISTRATOR.value,
        RoleEnums.OWNER.value
    ]
    can_read = can_edit or role == RoleEnums.CHIEF_ACCOUNTANT.value

    return can_edit, can_read


@need_permission(PermissionEnums.FINANCE_BUDGET)
def budget_list(request):
    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    period_type = request.GET.get('period_type', 'monthly')
    cat_type    = request.GET.get('cat_type', '')

    can_edit, _ = _get_budget_access(request.user)

    categories = BudgetCategory.objects.filter(
        parent=None, is_active=True
    ).prefetch_related('children')

    if cat_type:
        categories = categories.filter(category_type=cat_type)

    OVERRUN_THRESHOLD = 10 

    def _get_all_ids(cat):
        ids = [cat.pk]
        for child in cat.children.all():
            ids.extend(_get_all_ids(child))
        return ids

    def get_items_for_category(cat):
        qs = BudgetItem.objects.filter(
            category__id__in=_get_all_ids(cat),
            period_type=period_type,
            year=year,
        )
        if period_type == 'monthly':
            qs = qs.filter(month=month)

        plan     = sum(i.plan     for i in qs) or Decimal('0')
        fact     = sum(i.fact     for i in qs) or Decimal('0')
        forecast = sum(i.forecast for i in qs) or Decimal('0')
        
        variance = fact - plan
        
        exec_pct = round((fact / plan) * 100, 1) if plan and plan > 0 else (100.0 if fact else 0.0)
        
        is_expense = getattr(cat, 'category_type', '') == 'expense'
        overrun  = is_expense and exec_pct > (100 + OVERRUN_THRESHOLD)

        return {
            'plan': plan, 'fact': fact, 'forecast': forecast,
            'variance': variance, 'exec_pct': exec_pct, 'overrun': overrun,
        }

    rows = []
    total_plan = total_fact = Decimal('0')
    has_overrun = False

    for cat in categories:
        data = get_items_for_category(cat)
        rows.append({'cat': cat, **data})
        
        total_plan += data['plan']
        total_fact += data['fact']
        if data['overrun']:
            has_overrun = True

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
        
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        'rows':        rows,
        'year':        year,
        'month':       month,
        'period_type': period_type,
        'cat_type':    cat_type,
        'can_edit':    can_edit, 
        'has_overrun': has_overrun,
        'total_plan':  total_plan,
        'total_fact':  total_fact,
        'prev_year':   prev_year, 'prev_month': prev_month,
        'next_year':   next_year, 'next_month': next_month,
        'today':       today,
    }
    if request.GET.get('export') == 'xlsx':
        from .services.excel import export_budget
        all_ids = []
        for cat in categories:
            all_ids.extend(_get_all_ids(cat))
        export_qs = BudgetItem.objects.filter(
            category__id__in=all_ids,
            period_type=period_type,
            year=year,
        )
        if period_type == 'monthly':
            export_qs = export_qs.filter(month=month)
        return export_budget(export_qs.select_related('category'))

    return render(request, 'site/finances/budget/budget_list.html', context)


@need_permission(PermissionEnums.FINANCE_BUDGET)
def budget_detail(request, pk):
    category = get_object_or_404(BudgetCategory, pk=pk)
    can_edit, _ = _get_budget_access(request.user)

    items = BudgetItem.objects.filter(
        category=category
    ).order_by('year', 'month', 'quarter')

    rows = []
    for item in items:
        plan = item.plan or Decimal('0')
        fact = item.fact or Decimal('0')
        
        variance = fact - plan
        exec_pct = round((fact / plan) * 100, 1) if plan > 0 else (100.0 if fact else 0.0)
        overrun = (category.category_type == 'expense' and exec_pct > 110)

        rows.append({
            'item':      item,
            'variance':  variance,
            'exec_pct':  exec_pct,
            'overrun':   overrun,
        })

    context = {
        'category': category,
        'rows':     rows,
        'can_edit': can_edit,
    }
    return render(request, 'site/finances/budget/budget_detail.html', context)


@need_permission(PermissionEnums.FINANCE_BUDGET)
def budget_item_create(request, category_pk):
    can_edit, _ = _get_budget_access(request.user)
    if not can_edit:
        return HttpResponseForbidden("<h1>403 Forbidden</h1><p>Доступ на создание ограничен для вашей роли (Chief Accountant имеет доступ только на чтение).</p>")

    category = get_object_or_404(BudgetCategory, pk=category_pk)

    class BudgetItemForm(django_forms.ModelForm):
        class Meta:
            model  = BudgetItem
            fields = ['period_type', 'year', 'month', 'quarter', 'plan', 'fact', 'forecast', 'note']
            widgets = {
                'note': django_forms.Textarea(attrs={'rows': 2}),
            }

    form = BudgetItemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.category = category
        item.save()
        messages.success(request, 'Строка бюджета добавлена.')
        return redirect('finances:budget_detail', pk=category_pk)

    context = {
        'form':     form,
        'category': category,
        'title':    f'Добавить строку: {category.name}',
    }
    return render(request, 'site/finances/budget/budget_item_form.html', context)


@need_permission(PermissionEnums.FINANCE_BUDGET)
def budget_item_edit(request, pk):
    item     = get_object_or_404(BudgetItem, pk=pk)
    can_edit, _ = _get_budget_access(request.user)
    if not can_edit:
        return HttpResponseForbidden("<h1>403 Forbidden</h1><p>Редактирование доступно только CFO.</p>")

    class BudgetItemForm(django_forms.ModelForm):
        class Meta:
            model  = BudgetItem
            fields = ['period_type', 'year', 'month', 'quarter', 'plan', 'fact', 'forecast', 'note']
            widgets = {
                'note': django_forms.Textarea(attrs={'rows': 2}),
            }

    form = BudgetItemForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Строка бюджета обновлена.')
        return redirect('finances:budget_detail', pk=item.category.pk)

    context = {
        'form':     form,
        'category': item.category,
        'title':    f'Редактировать: {item.category.name}',
        'item':     item,
    }
    return render(request, 'site/finances/budget/budget_item_form.html', context)


@need_permission(PermissionEnums.FINANCE_BUDGET)
def budget_item_delete(request, pk):
    item = get_object_or_404(BudgetItem, pk=pk)
    can_edit, _ = _get_budget_access(request.user)
    if not can_edit:
        return HttpResponseForbidden("<h1>403 Forbidden</h1><p>Удаление доступно только CFO.</p>")

    category_pk = item.category.pk
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Строка бюджета удалена.')
    return redirect('finances:budget_detail', pk=category_pk)


# ── FE-5.5: ОПиУ / ДДС / Кредитная модель ────────────────────────────────────

def _variance_pct(plan, fact):
    if not plan or plan == 0:
        return None
    return round((fact - plan) / plan * 100, 1)


def _build_opiu_rows(statement):
    """Строит строки таблицы ОПиУ из FinancialStatement."""
    if not statement:
        return []

    def row(label, plan, fact, forecast=None, margin_fact=None):
        is_margin = margin_fact is not None
        if is_margin:
            return {
                'label': label,
                'plan': None,
                'fact': margin_fact,
                'forecast': None,
                'variance': None,
                'variance_pct': None,
                'margin_fact': margin_fact,
                'is_margin': True,
            }
        variance = fact - plan
        return {
            'label': label,
            'plan': plan,
            'fact': fact,
            'forecast': forecast,
            'variance': variance,
            'variance_pct': _variance_pct(plan, fact),
            'margin_fact': None,
            'is_margin': False,
        }

    rows = [
        row('Выручка', statement.revenue_plan, statement.revenue_fact, statement.revenue_forecast),
        row('EBITDA', statement.ebitda_plan, statement.ebitda_fact, statement.ebitda_forecast),
        row(
            'Операционная прибыль',
            statement.operating_profit_plan,
            statement.operating_profit_fact,
        ),
        row('Чистая прибыль', statement.net_profit_plan, statement.net_profit_fact, statement.net_profit_forecast),
    ]
    rows.append(row(
        'Рентабельность (чистая), %',
        None,
        statement.net_profit_fact,
        margin_fact=statement.net_margin_fact,
    ))
    return rows


@need_permission(PermissionEnums.FINANCE_REPORTS)
def financial_statement(request):
    today = date.today()
    try:
        year  = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    period_type = request.GET.get('period_type', FinancialStatement.Period.MONTHLY)

    qs = FinancialStatement.objects.filter(
        period_type=period_type,
        year=year,
    )
    if period_type == FinancialStatement.Period.MONTHLY:
        qs = qs.filter(month=month)
    statement = qs.first()

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        'statement':   statement,
        'rows':        _build_opiu_rows(statement),
        'year':        year,
        'month':       month,
        'period_type': period_type,
        'period_choices': FinancialStatement.Period.choices,
        'prev_year':   prev_year,
        'prev_month':  prev_month,
        'next_year':   next_year,
        'next_month':  next_month,
    }
    if request.GET.get('export') == 'xlsx':
        from .services.excel import export_financial_statement
        export_qs = FinancialStatement.objects.filter(period_type=period_type, year=year)
        if period_type == FinancialStatement.Period.MONTHLY:
            export_qs = export_qs.filter(month=month)
        return export_financial_statement(export_qs)

    return render(request, 'site/finances/opiu.html', context)


@need_permission(PermissionEnums.FINANCE_REPORTS)
def cashflow_register(request):
    today = date.today()
    date_from = request.GET.get('date_from') or today.replace(day=1).isoformat()
    date_to   = request.GET.get('date_to') or today.isoformat()
    direction = request.GET.get('direction', '')
    flow_type = request.GET.get('flow_type', '')
    counterparty_id = request.GET.get('counterparty', '')

    qs = CashFlowRecord.objects.select_related('counterparty', 'budget_category').all()

    try:
        qs = qs.filter(transaction_date__gte=date.fromisoformat(date_from))
        qs = qs.filter(transaction_date__lte=date.fromisoformat(date_to))
    except ValueError:
        pass

    if direction:
        qs = qs.filter(direction=direction)
    if flow_type:
        qs = qs.filter(flow_type=flow_type)
    if counterparty_id:
        qs = qs.filter(counterparty_id=counterparty_id)

    if request.GET.get('export') == 'xlsx':
        from .services.excel import export_cashflow
        return export_cashflow(qs.order_by('-transaction_date', '-created_at'))

    records = qs.order_by('-transaction_date', '-created_at')[:500]

    total_inflow = sum(r.amount for r in records if r.direction == CashFlowRecord.Direction.INFLOW)
    total_outflow = sum(r.amount for r in records if r.direction == CashFlowRecord.Direction.OUTFLOW)

    from onec.models import Counterparty
    counterparties = Counterparty.objects.order_by('short_name')[:200]

    context = _finance_filter_context({
        'records':        records,
        'date_from':      date_from,
        'date_to':        date_to,
        'f_direction':    direction,
        'f_flow_type':    flow_type,
        'f_counterparty': counterparty_id,
        'directions':     CashFlowRecord.Direction.choices,
        'flow_types':     CashFlowRecord.FlowType.choices,
        'counterparties': counterparties,
        'total_inflow':   total_inflow,
        'total_outflow':  total_outflow,
        'net_flow':       total_inflow - total_outflow,
    })
    return render(request, 'site/finances/cashflow.html', context)


def _can_manage_credit(user):
    role = user.role.value if hasattr(user.role, 'value') else user.role
    return role in (RoleEnums.CFO.value, RoleEnums.OWNER.value, RoleEnums.ADMINISTRATOR.value)


# ── BE-6.1: Executive Dashboard ───────────────────────────────────────────────

def _compute_dashboard_kpis(request=None):
    import calendar
    from datetime import timedelta
    from django.db.models import Sum

    from .services.session_filters import (
        cash_balance_date_bounds,
        filter_calendar,
        filter_cashflow,
        filter_registry,
        get_filters,
        has_active_filters,
        parse_filter_date,
    )

    filters = get_filters(request)
    today = date.today()
    first_day_this_month = today.replace(day=1)
    period_from = parse_filter_date(filters.get('period_from'))
    period_to = parse_filter_date(filters.get('period_to'))
    custom_period = bool(period_from or period_to)

    if today.month == 1:
        first_day_prev_month = date(today.year - 1, 12, 1)
        last_day_prev_month  = date(today.year - 1, 12, 31)
    else:
        first_day_prev_month = today.replace(month=today.month - 1, day=1)
        last_day_prev_month = today.replace(
            month=today.month - 1,
            day=calendar.monthrange(today.year, today.month - 1)[1],
        )

    cash_start, cash_end = cash_balance_date_bounds(filters, today)
    cash_qs = filter_calendar(
        PaymentCalendarEntry.objects.filter(
            status=PaymentCalendarEntry.Status.FACT,
            actual_date__gte=cash_start,
            actual_date__lte=cash_end,
        ),
        filters,
    )
    cash_balance = cash_qs.aggregate(total=Sum('actual_amount'))['total'] or Decimal('0')

    registry_qs = filter_registry(TenantPaymentRegistry.objects.all(), filters)

    if custom_period:
        revenue_mtd = registry_qs.aggregate(total=Sum('paid'))['total'] or Decimal('0')
        revenue_mtd_change = 0.0
        revenue_ytd = revenue_mtd
    else:
        revenue_mtd = registry_qs.filter(
            period__year=today.year,
            period__month=today.month,
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')

        revenue_prev = filter_registry(
            TenantPaymentRegistry.objects.all(), filters,
        ).filter(
            period__year=first_day_prev_month.year,
            period__month=first_day_prev_month.month,
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')

        if revenue_prev and revenue_prev != 0:
            revenue_mtd_change = float(
                (revenue_mtd - revenue_prev) / revenue_prev * 100
            )
        else:
            revenue_mtd_change = 0.0

        revenue_ytd = registry_qs.filter(
            period__year=today.year,
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')

    if custom_period:
        exp_start, exp_end = period_from or cash_start, period_to or today
    else:
        exp_start, exp_end = first_day_this_month, today

    expenses_mtd = filter_cashflow(
        CashFlowRecord.objects.filter(
            direction=CashFlowRecord.Direction.OUTFLOW,
            transaction_date__gte=exp_start,
            transaction_date__lte=exp_end,
        ),
        filters,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    net_cf = revenue_mtd - expenses_mtd

    from django.db.models import F
    budget_items = BudgetItem.objects.filter(
        year=today.year,
        month=today.month,
        period_type=BudgetItem.Period.MONTHLY,
    )
    total_plan = sum(i.plan for i in budget_items) or Decimal('0')
    total_fact = sum(i.fact for i in budget_items) or Decimal('0')
    if total_plan and total_plan != 0:
        budget_deviation_pct = float((total_fact - total_plan) / total_plan * 100)
    else:
        budget_deviation_pct = 0.0

    overdue_qs = filter_registry(
        TenantPaymentRegistry.objects.filter(status=TenantPaymentRegistry.Status.OVERDUE),
        filters,
    )
    overdue_count  = overdue_qs.count()
    overdue_amount = overdue_qs.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0')

    return {
        'cash_balance': cash_balance,
        'revenue_mtd': revenue_mtd,
        'revenue_ytd': revenue_ytd,
        'revenue_mtd_change': round(revenue_mtd_change, 2),
        'expenses_mtd': expenses_mtd,
        'net_cf': net_cf,
        'budget_deviation_pct': round(budget_deviation_pct, 2),
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'today': today,
        'finance_filters_active': has_active_filters(filters),
    }


@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def dashboard(request):
    context = _finance_filter_context(_compute_dashboard_kpis(request))
    context['can_manage'] = _can_manage_credit(request.user)
    return render(request, 'site/finances/dashboard.html', context)


@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def dashboard_kpi(request):
    kpis = _compute_dashboard_kpis(request)
    return JsonResponse({
        'cash_balance': float(kpis['cash_balance']),
        'revenue_mtd': float(kpis['revenue_mtd']),
        'revenue_ytd': float(kpis['revenue_ytd']),
        'revenue_mtd_change': kpis['revenue_mtd_change'],
        'expenses_mtd': float(kpis['expenses_mtd']),
        'net_cf': float(kpis['net_cf']),
        'budget_deviation_pct': kpis['budget_deviation_pct'],
        'overdue_count': kpis['overdue_count'],
        'overdue_amount': float(kpis['overdue_amount']),
    })


@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def dashboard_drilldown(request):
    from django.db.models import Sum

    from .services.session_filters import (
        filter_calendar,
        filter_cashflow,
        filter_registry,
        get_filters,
    )

    filters = get_filters(request)
    drill_type = request.GET.get('type', '')
    period_str = request.GET.get('period', '')

    try:
        if period_str:
            parts = period_str.split('-')
            drill_year  = int(parts[0])
            drill_month = int(parts[1]) if len(parts) > 1 else None
        else:
            drill_year  = date.today().year
            drill_month = date.today().month
    except (ValueError, IndexError):
        drill_year  = date.today().year
        drill_month = date.today().month

    data = []

    if drill_type in ('revenue', 'revenue_ytd'):
        qs = filter_registry(
            TenantPaymentRegistry.objects.select_related('tenant').filter(
                period__year=drill_year,
            ),
            filters,
        )
        if drill_type == 'revenue' and drill_month:
            qs = qs.filter(period__month=drill_month)
        data = [
            {
                'id': r.id,
                'tenant': str(r.tenant),
                'contract_number': r.contract_number,
                'period': str(r.period),
                'paid': float(r.paid),
                'charged': float(r.charged),
                'status': r.status,
            }
            for r in qs
        ]

    elif drill_type == 'cash':
        qs = filter_calendar(
            PaymentCalendarEntry.objects.select_related('tenant').filter(
                status=PaymentCalendarEntry.Status.FACT,
                actual_date__year=drill_year,
            ),
            filters,
        )
        if drill_month:
            qs = qs.filter(actual_date__month=drill_month)
        data = [
            {
                'id': e.id,
                'tenant': str(e.tenant),
                'date': str(e.actual_date),
                'amount': float(e.actual_amount),
                'contract': e.contract_number,
            }
            for e in qs if e.actual_date
        ]

    elif drill_type == 'net_cf':
        inflows = filter_registry(
            TenantPaymentRegistry.objects.select_related('tenant').filter(
                period__year=drill_year,
            ),
            filters,
        )
        if drill_month:
            inflows = inflows.filter(period__month=drill_month)
        for r in inflows:
            data.append({
                'type': 'поступление',
                'tenant': str(r.tenant),
                'period': str(r.period),
                'amount': float(r.paid),
            })
        outflows = filter_cashflow(
            CashFlowRecord.objects.filter(
                direction=CashFlowRecord.Direction.OUTFLOW,
                transaction_date__year=drill_year,
            ),
            filters,
        )
        if drill_month:
            outflows = outflows.filter(transaction_date__month=drill_month)
        for r in outflows:
            data.append({
                'type': 'расход',
                'date': str(r.transaction_date),
                'description': r.description or '',
                'amount': -float(r.amount),
            })

    elif drill_type == 'expenses':
        qs = filter_cashflow(
            CashFlowRecord.objects.filter(
                direction=CashFlowRecord.Direction.OUTFLOW,
                transaction_date__year=drill_year,
            ),
            filters,
        )
        if drill_month:
            qs = qs.filter(transaction_date__month=drill_month)
        data = [
            {
                'id': r.id,
                'date': str(r.transaction_date),
                'amount': float(r.amount),
                'description': r.description or '',
                'flow_type': r.flow_type,
            }
            for r in qs
        ]

    elif drill_type == 'overdue':
        qs = filter_registry(
            TenantPaymentRegistry.objects.select_related('tenant').filter(
                status=TenantPaymentRegistry.Status.OVERDUE,
            ),
            filters,
        )
        data = [
            {
                'id': r.id,
                'tenant': str(r.tenant),
                'contract_number': r.contract_number,
                'period': str(r.period),
                'balance': float(r.balance),
                'overdue_days': r.overdue_days,
            }
            for r in qs
        ]

    elif drill_type == 'budget':
        qs = BudgetItem.objects.select_related('category').filter(
            year=drill_year,
        )
        if drill_month:
            qs = qs.filter(month=drill_month, period_type=BudgetItem.Period.MONTHLY)
        data = [
            {
                'id': item.id,
                'category': str(item.category),
                'period': item.get_period_label(),
                'plan': float(item.plan),
                'fact': float(item.fact),
                'variance': float(item.variance),
                'variance_pct': item.variance_pct,
            }
            for item in qs
        ]

    return JsonResponse({'type': drill_type, 'period': period_str, 'data': data})


@need_permission(PermissionEnums.FINANCE_SCENARIOS)
def credit_model_list(request):
    models_qs = CreditModel.objects.all()
    can_create = _can_manage_credit(request.user)

    context = {
        'credit_models': models_qs,
        'can_create':    can_create,
        'scenario_choices': CreditModel.Scenario.choices,
    }
    return render(request, 'site/finances/credit_model.html', context)


@need_permission(PermissionEnums.FINANCE_SCENARIOS)
def credit_model_create(request):
    if not _can_manage_credit(request.user):
        return HttpResponseForbidden('<h1>403</h1><p>Кредитная модель доступна только CFO.</p>')

    import json

    class CreditModelForm(django_forms.ModelForm):
        projected_income_json   = django_forms.CharField(
            label='Прогноз доходов (JSON)', required=False,
        )
        projected_expenses_json = django_forms.CharField(
            label='Прогноз расходов (JSON)', required=False,
        )
        projected_cashflow_json = django_forms.CharField(
            label='Прогноз ДДС (JSON)', required=False,
        )

        class Meta:
            model = CreditModel
            fields = [
                'name', 'scenario', 'period_start', 'period_end',
                'loan_amount', 'loan_rate',
            ]
            widgets = {
                'name': django_forms.TextInput(attrs={
                    'class': 'fin-input',
                    'placeholder': 'Например: Базовый сценарий Q2',
                }),
                'scenario': django_forms.Select(attrs={'class': 'fin-input'}),
                'period_start': django_forms.DateInput(attrs={
                    'type': 'date', 'class': 'fin-input',
                }),
                'period_end': django_forms.DateInput(attrs={
                    'type': 'date', 'class': 'fin-input',
                }),
                'loan_amount': django_forms.NumberInput(attrs={
                    'class': 'fin-input', 'step': '0.01', 'min': '0',
                }),
                'loan_rate': django_forms.NumberInput(attrs={
                    'class': 'fin-input', 'step': '0.01', 'min': '0',
                }),
                'projected_income_json': django_forms.Textarea(attrs={
                    'class': 'fin-input fin-textarea',
                    'rows': 4,
                    'placeholder': '{"2026-05": 15000000}',
                }),
                'projected_expenses_json': django_forms.Textarea(attrs={
                    'class': 'fin-input fin-textarea',
                    'rows': 4,
                }),
                'projected_cashflow_json': django_forms.Textarea(attrs={
                    'class': 'fin-input fin-textarea',
                    'rows': 4,
                }),
            }

        def _parse_json_field(self, raw, field_name):
            if not raw or not raw.strip():
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise django_forms.ValidationError(f'Некорректный JSON в поле {field_name}')

        def clean(self):
            cleaned = super().clean()
            cleaned['projected_income']   = self._parse_json_field(
                cleaned.get('projected_income_json', ''), 'доходов'
            )
            cleaned['projected_expenses'] = self._parse_json_field(
                cleaned.get('projected_expenses_json', ''), 'расходов'
            )
            cleaned['projected_cashflow'] = self._parse_json_field(
                cleaned.get('projected_cashflow_json', ''), 'ДДС'
            )
            return cleaned

    form = CreditModelForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cm = form.save(commit=False)
        cm.projected_income   = form.cleaned_data['projected_income']
        cm.projected_expenses = form.cleaned_data['projected_expenses']
        cm.projected_cashflow = form.cleaned_data['projected_cashflow']
        cm.calculate_dscr()
        cm.save()
        messages.success(request, f'Сценарий «{cm.name}» создан. DSCR: {cm.dscr or "—"}')
        return redirect('finances:credit_model_list')

    context = {
        'form':       form,
        'title':      'Новый кредитный сценарий',
        'show_form':  True,
    }
    return render(request, 'site/finances/credit_model.html', context)


# ── BE-6.4: Аналитика аренды ──────────────────────────────────────────────────

@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def rent_analytics(request):
    from django.db.models import Sum
    from tenants.models import Tenant

    today = date.today()
    current_year = today.year

    ytd_qs = TenantPaymentRegistry.objects.filter(
        period__year=current_year
    ).values('tenant').annotate(total_paid=Sum('paid')).order_by('-total_paid')

    tenant_ids = [row['tenant'] for row in ytd_qs]
    tenants_map = {t.pk: t for t in Tenant.objects.filter(pk__in=tenant_ids)}

    top_tenants = []
    for row in ytd_qs[:10]:
        t = tenants_map.get(row['tenant'])
        top_tenants.append({
            'tenant': t,
            'total_paid': row['total_paid'],
        })

    all_tenants = Tenant.objects.all()
    total_area = sum(t.area or 0 for t in all_tenants)
    occupied_tenant_ids = set(
        TenantPaymentRegistry.objects.filter(
            period__year=current_year
        ).values_list('tenant_id', flat=True).distinct()
    )
    occupied_area = sum(
        t.area or 0 for t in all_tenants if t.pk in occupied_tenant_ids
    )
    if total_area > 0:
        vacancy_rate = round((total_area - occupied_area) / total_area * 100, 2)
    else:
        vacancy_rate = 0

    if occupied_area > 0:
        total_revenue_ytd = sum(row['total_paid'] or 0 for row in ytd_qs)
        avg_rate_per_sqm = round(float(total_revenue_ytd) / occupied_area, 2) if occupied_area else 0
    else:
        avg_rate_per_sqm = 0
        total_revenue_ytd = 0

    overdue_qs = TenantPaymentRegistry.objects.filter(
        status=TenantPaymentRegistry.Status.OVERDUE
    ).values('tenant').annotate(total_debt=Sum('balance')).order_by('-total_debt')

    overdue_tenant_ids = [row['tenant'] for row in overdue_qs]
    overdue_tenants_map = {t.pk: t for t in Tenant.objects.filter(pk__in=overdue_tenant_ids)}

    top_debtors = []
    total_overdue = 0
    for row in overdue_qs:
        t = overdue_tenants_map.get(row['tenant'])
        debt = row['total_debt'] or 0
        total_overdue += float(debt)
        top_debtors.append({
            'tenant': t,
            'total_debt': debt,
        })

    from django.db.models.functions import TruncMonth
    dynamics_qs = (
        TenantPaymentRegistry.objects
        .annotate(month=TruncMonth('period'))
        .values('month')
        .annotate(total_paid=Sum('paid'))
        .order_by('month')
    )
    all_periods = list(dynamics_qs)
    last_6 = all_periods[-6:] if len(all_periods) >= 6 else all_periods

    rent_dynamics = {
        'labels': [row['month'].strftime('%Y-%m') for row in last_6],
        'actual': [float(row['total_paid'] or 0) for row in last_6],
    }

    max_paid = max((float(row['total_paid'] or 0) for row in top_tenants), default=0)
    top_tenants_rows = []
    for row in top_tenants:
        paid = float(row['total_paid'] or 0)
        share = round(paid / max_paid * 100, 1) if max_paid > 0 else 0
        top_tenants_rows.append({
            'tenant': row['tenant'],
            'total_paid': row['total_paid'],
            'share_pct': share,
        })

    tenant_chart = {
        'labels': [
            (row['tenant'].name if row['tenant'] else '—')
            for row in top_tenants
        ],
        'values': [float(row['total_paid'] or 0) for row in top_tenants],
    }

    context = {
        'top_tenants': top_tenants_rows,
        'vacancy_rate': vacancy_rate,
        'avg_rate_per_sqm': avg_rate_per_sqm,
        'top_debtors': top_debtors,
        'rent_dynamics': rent_dynamics,
        'tenant_chart': tenant_chart,
        'total_revenue_ytd': total_revenue_ytd,
        'total_overdue': total_overdue,
        'today': today,
        'tenants_count': all_tenants.count(),
        'occupied_count': len(occupied_tenant_ids),
    }
    return render(request, 'site/finances/rent_analytics.html', context)


# ── BE-6.8: Global finance filters ────────────────────────────────────────────

@_login_required
def save_finance_filters(request):
    if request.method == 'POST':
        import json
        try:
            filters = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        request.session['finance_filters'] = {
            'company':     filters.get('company', ''),
            'tenant':      filters.get('tenant', ''),
            'category':    filters.get('category', ''),
            'period_from': filters.get('period_from', ''),
            'period_to':   filters.get('period_to', ''),
        }
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)


@_login_required
def get_finance_filters(request):
    filters = request.session.get('finance_filters', {})
    return JsonResponse(filters)


# ── BE-6.9: Multi-currency balances ───────────────────────────────────────────

@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def dashboard_balances(request):
    from .services.balances import get_balances_with_conversion
    currency = request.GET.get('currency', 'USD').upper()
    allowed  = {'USD', 'EUR', 'RUB', 'CNY', 'KZT'}
    if currency not in allowed:
        return JsonResponse({'error': f'Unsupported currency: {currency}'}, status=400)
    if currency == 'KZT':
        return JsonResponse({'error': 'Use KZT as base currency; select USD, EUR, RUB or CNY'}, status=400)
    data = get_balances_with_conversion(currency=currency)
    return JsonResponse(data)


# ── BE-6.2: CF chart endpoints ────────────────────────────────────────────────

@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def cashflow_daily(request):
    from datetime import timedelta
    from django.db.models import Sum

    from .services.session_filters import filter_calendar, filter_cashflow, get_filters

    filters = get_filters(request)
    days = max(1, min(int(request.GET.get('days', 30)), 365))
    today = date.today()
    start = today - timedelta(days=days - 1)

    date_range = [start + timedelta(days=i) for i in range(days)]

    cf_rows = (
        filter_cashflow(
            CashFlowRecord.objects.filter(
                transaction_date__gte=start,
                transaction_date__lte=today,
            ),
            filters,
        )
        .values('transaction_date', 'direction')
        .annotate(total=Sum('amount'))
    )

    inflow_map  = {}
    outflow_map = {}
    for row in cf_rows:
        d = row['transaction_date']
        if row['direction'] == CashFlowRecord.Direction.INFLOW:
            inflow_map[d] = float(row['total'] or 0)
        else:
            outflow_map[d] = float(row['total'] or 0)

    calendar_rows = (
        filter_calendar(
            PaymentCalendarEntry.objects.filter(
                status=PaymentCalendarEntry.Status.FACT,
                actual_date__gte=start,
                actual_date__lte=today,
            ),
            filters,
        )
        .values('actual_date')
        .annotate(total=Sum('actual_amount'))
    )
    for row in calendar_rows:
        d = row['actual_date']
        inflow_map[d] = inflow_map.get(d, 0) + float(row['total'] or 0)

    labels  = [d.isoformat() for d in date_range]
    income  = [inflow_map.get(d, 0) for d in date_range]
    expense = [outflow_map.get(d, 0) for d in date_range]
    net     = [i - e for i, e in zip(income, expense)]

    return JsonResponse({'labels': labels, 'income': income, 'expense': expense, 'net': net})


@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def cashflow_weekly(request):
    from datetime import timedelta
    from django.db.models import Sum

    from .services.session_filters import filter_calendar, filter_cashflow, get_filters

    filters = get_filters(request)
    weeks = max(1, min(int(request.GET.get('weeks', 12)), 52))
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    start  = monday - timedelta(weeks=weeks - 1)

    week_starts = [start + timedelta(weeks=i) for i in range(weeks)]

    cf_rows = (
        filter_cashflow(
            CashFlowRecord.objects.filter(
                transaction_date__gte=start,
                transaction_date__lte=today,
            ),
            filters,
        )
        .values('transaction_date', 'direction')
        .annotate(total=Sum('amount'))
    )

    inflow_by_date  = {}
    outflow_by_date = {}
    for row in cf_rows:
        d = row['transaction_date']
        if row['direction'] == CashFlowRecord.Direction.INFLOW:
            inflow_by_date[d] = float(row['total'] or 0)
        else:
            outflow_by_date[d] = float(row['total'] or 0)

    calendar_rows = (
        filter_calendar(
            PaymentCalendarEntry.objects.filter(
                status=PaymentCalendarEntry.Status.FACT,
                actual_date__gte=start,
                actual_date__lte=today,
            ),
            filters,
        )
        .values('actual_date')
        .annotate(total=Sum('actual_amount'))
    )
    for row in calendar_rows:
        d = row['actual_date']
        inflow_by_date[d] = inflow_by_date.get(d, 0) + float(row['total'] or 0)

    labels  = []
    income  = []
    expense = []
    net     = []

    for ws in week_starts:
        from datetime import timedelta as td
        we = ws + td(days=6)
        week_income  = sum(v for d, v in inflow_by_date.items() if ws <= d <= we)
        week_expense = sum(v for d, v in outflow_by_date.items() if ws <= d <= we)
        labels.append(ws.isoformat())
        income.append(week_income)
        expense.append(week_expense)
        net.append(week_income - week_expense)

    return JsonResponse({'labels': labels, 'income': income, 'expense': expense, 'net': net})


# ── BE-6.3: Drill-down до документа 1С ───────────────────────────────────────

@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def drilldown_record(request, onec_id):
    record = get_object_or_404(CashFlowRecord, onec_id=onec_id)

    counterparty = None
    try:
        from onec.models import Counterparty
        counterparty = Counterparty.objects.filter(id_1c=onec_id).first()
    except Exception:
        pass

    return JsonResponse({
        'record': {
            'id': record.id,
            'date': str(record.transaction_date),
            'amount': float(record.amount),
            'direction': record.direction,
            'flow_type': record.flow_type,
            'description': record.description or '',
            'onec_id': record.onec_id,
            'document_number': record.document_number or '',
        },
        'counterparty_url': f'/onec/counterparties/{counterparty.pk}/' if counterparty else None,
        'counterparty_name': counterparty.full_name if counterparty else None,
    })


# ── BE-6.5: Прогноз CF ────────────────────────────────────────────────────────

@need_permission(PermissionEnums.FINANCE_DASHBOARD)
def cashflow_forecast(request):
    from .services.forecast import forecast_cashflow
    try:
        days = max(1, min(int(request.GET.get('days', 90)), 365))
    except (ValueError, TypeError):
        days = 90
    data = forecast_cashflow(horizon_days=days)
    return JsonResponse(data)


# ── BE-6.6: Сценарии (редирект на кредитную модель) ───────────────────────────

@need_permission(PermissionEnums.FINANCE_SCENARIOS)
def scenarios_list(request):
    return redirect('finances:credit_model_list')


@need_permission(PermissionEnums.FINANCE_SCENARIOS)
def scenario_detail_json(request, pk):
    scenario = get_object_or_404(CreditModel, pk=pk)

    return JsonResponse({
        'id': scenario.id,
        'name': scenario.name,
        'scenario': scenario.scenario,
        'period_start': str(scenario.period_start),
        'period_end': str(scenario.period_end),
        'loan_amount': float(scenario.loan_amount),
        'loan_rate': float(scenario.loan_rate),
        'dscr': float(scenario.dscr) if scenario.dscr is not None else None,
        'free_cashflow': float(scenario.free_cashflow) if scenario.free_cashflow is not None else None,
        'risk_level': scenario.risk_level,
        'projected_cashflow': scenario.projected_cashflow,
    })