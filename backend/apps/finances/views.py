from django.shortcuts import redirect, render, get_object_or_404
from account.role_permissions import need_permission, PermissionEnums
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from decimal import Decimal
from django import forms as django_forms

from project.utils import get_or_none

from .forms import FinanceItemForm, GeneratedInvoiceForm, GeneratedInvoiceItemFormSet
from .models import FinanceItem, TenantPaymentRegistry, GeneratedInvoice, BudgetCategory, BudgetItem, FinancialStatement, CashFlowRecord, CreditModel
from .serializers import FinanceItemSerializer

from datetime import date
from django.db.models import Q
from django.utils import timezone

from account.role_permissions import RoleEnums

from finances.services.notifications import send_invoice as _send_invoice

def payment_reg(request):
    context = {

    }

    return render(request, 'site/finances/payment_register.html', context)



@need_permission(PermissionEnums.FINANCES)
def calendar(request):
    context = {

    }

    return render(request, 'site/finances/calendar.html', context)


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



def budget_list(request):
    context = {

    }

    return render(request, 'site/finances/budget/budget_list.html', context)


def budget(request, pk):
    context = {

    }

    return render(request, 'site/finances/budget/budget.html', context)


def budget_create(request):
    context = {

    }

    return render(request, 'site/finances/budget/budget_create.html', context)


def bill(request):
    context = {

    }

    return render(request, 'site/finances/bill.html', context)


@need_permission(PermissionEnums.FINANCES)
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

    context = {
        'entries': entries,
        'tenants': tenants,
        'statuses': statuses,
        'today': date.today(),

        'f_search': search,
        'f_status': status,
        'f_tenant': tenant_id,
        'f_period_from': period_from,
        'f_period_to': period_to,
    }

    return render(request, 'site/finances/payment_register.html', context)

@need_permission(PermissionEnums.FINANCES)
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


@need_permission(PermissionEnums.FINANCES)
def payment_calendar_day(request, year, month, day):
    from datetime import date
    from .models import PaymentCalendarEntry

    try:
        day_date = date(year, month, day)
    except ValueError:
        from django.http import Http404
        raise Http404

    entries = PaymentCalendarEntry.objects.select_related(
        'tenant', 'tenant__room'
    ).filter(expected_date=day_date).order_by('tenant__name')

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

    if request.method != 'POST':
        return redirect('finances:invoice_detail', pk=pk)

    if invoice.status != GeneratedInvoice.Status.CREATED:
        messages.error(request, 'Счёт уже отправлен или отменён.')
        return redirect('finances:invoice_detail', pk=pk)

    sent_via = request.POST.get('sent_via', GeneratedInvoice.SentVia.EMAIL)
    contact  = request.POST.get('contact', '').strip() or None

    success = _send_invoice(invoice, sent_via=sent_via, contact=contact)

    if success:
        invoice.refresh_from_db()
        if invoice.status != GeneratedInvoice.Status.SENT:
            invoice.status   = GeneratedInvoice.Status.SENT
            invoice.sent_via = sent_via
            invoice.sent_at  = timezone.now()
            invoice.save()
        messages.success(request, f'Счёт №{invoice.number} отправлен.')
    else:
        messages.warning(request, f'Счёт №{invoice.number} — отправка не выполнена.')

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
        invoice.status = GeneratedInvoice.Status.PAID
        invoice.save()
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
def budget_item_create_general(request):
    can_edit, _ = _get_budget_access(request.user)
    if not can_edit:
        return HttpResponseForbidden(
            "<h1>403 Forbidden</h1><p>Доступ на создание ограничен для вашей роли.</p>"
        )

    class GeneralBudgetItemForm(django_forms.ModelForm):
        class Meta:
            model = BudgetItem
            fields = ['category', 'period_type', 'year', 'month', 'quarter', 'plan', 'fact', 'forecast', 'note']
            widgets = {
                'note': django_forms.Textarea(attrs={'rows': 2}),
            }

    form = GeneralBudgetItemForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        item = form.save()  
        messages.success(request, 'Строка бюджета добавлена.')
        return redirect('finances:budget_detail', pk=item.category.pk)

    context = {
        'form': form,
        'title': 'Создать новую строку бюджета',
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

def opiu_list(request):
    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    period_type = request.GET.get('period_type', 'monthly')

    qs = FinancialStatement.objects.all()

    if period_type == 'monthly':
        qs = qs.filter(period_type='monthly', year=year, month=month)
    elif period_type == 'quarterly':
        quarter = (month - 1) // 3 + 1
        qs = qs.filter(period_type='quarterly', year=year, quarter=quarter)
    else:
        qs = qs.filter(period_type='yearly', year=year)

    statement = qs.first()

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    all_statements = FinancialStatement.objects.order_by('-year', '-month', '-quarter')

    context = {
        'statement':    statement,
        'year':         year,
        'month':        month,
        'month_name':   _month_name(month),
        'period_type':  period_type,
        'prev_year':    prev_year,  'prev_month':  prev_month,
        'next_year':    next_year,  'next_month':  next_month,
        'all_statements': all_statements,
    }
    return render(request, 'site/finances/opiu.html', context)


def cashflow_list(request):
    from datetime import datetime
    today = date.today()

    date_from_raw = request.GET.get('date_from', '').strip()
    date_to_raw   = request.GET.get('date_to',   '').strip()
    direction     = request.GET.get('direction', '')
    flow_type     = request.GET.get('flow_type', '')
    search        = request.GET.get('q', '').strip()

    def parse_date(s):
        for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(s, fmt).date()
            except (ValueError, TypeError):
                pass
        return None

    date_from = parse_date(date_from_raw)
    date_to   = parse_date(date_to_raw)

    qs = CashFlowRecord.objects.select_related(
        'counterparty', 'budget_category'
    ).order_by('-transaction_date', '-created_at')

    if date_from:
        qs = qs.filter(transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(transaction_date__lte=date_to)
    if direction:
        qs = qs.filter(direction=direction)
    if flow_type:
        qs = qs.filter(flow_type=flow_type)
    if search:
        qs = qs.filter(
            Q(description__icontains=search) |
            Q(document_number__icontains=search) |
            Q(counterparty__short_name__icontains=search)
        )

    from django.db.models import Sum
    totals = qs.aggregate(
        total_inflow=Sum('amount', filter=Q(direction='inflow')),
        total_outflow=Sum('amount', filter=Q(direction='outflow')),
    )
    total_inflow  = totals['total_inflow']  or Decimal('0')
    total_outflow = totals['total_outflow'] or Decimal('0')
    net_flow      = total_inflow - total_outflow

    context = {
        'records':       qs,
        'total_inflow':  total_inflow,
        'total_outflow': total_outflow,
        'net_flow':      net_flow,
        'directions':    CashFlowRecord.Direction.choices,
        'flow_types':    CashFlowRecord.FlowType.choices,
        'f_date_from':   date_from_raw,
        'f_date_to':     date_to_raw,
        'f_direction':   direction,
        'f_flow_type':   flow_type,
        'f_q':           search,
        'today':         today,
    }
    return render(request, 'site/finances/cashflow.html', context)



def credit_model_detail(request, pk):
    cm = get_object_or_404(
        CreditModel.objects.select_related('financial_statement'),
        pk=pk
    )

    scenarios = CreditModel.objects.filter(
        name=cm.name, year=cm.year
    ).order_by('scenario')

    DSCR_COLORS = {
        'excellent':  'success',
        'good':       'info',
        'acceptable': 'warning',
        'critical':   'danger',
        'unknown':    'secondary',
    }

    context = {
        'cm':          cm,
        'scenarios':   scenarios,
        'dscr_color':  DSCR_COLORS.get(cm.dscr_status, 'secondary'),
    }
    return render(request, 'site/finances/credit_model_detail.html', context)

def invoice_track_viewed(request, pk):
    from django.http import HttpResponse
    from finances.models import GeneratedInvoice
    from finances.services.notifications import mark_invoice_viewed
 
    try:
        invoice = GeneratedInvoice.objects.get(pk=pk)
        mark_invoice_viewed(invoice)
    except GeneratedInvoice.DoesNotExist:
        pass
 
    TRANSPARENT_GIF = (
        b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
        b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00'
        b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
        b'\x44\x01\x00\x3b'
    )
    return HttpResponse(TRANSPARENT_GIF, content_type='image/gif')

def credit_model_list(request):
    scenario   = request.GET.get('scenario', '')
    risk_level = request.GET.get('risk_level', '')
    year       = request.GET.get('year', '')

    qs = CreditModel.objects.select_related('financial_statement').order_by('-year', 'scenario')

    if scenario:
        qs = qs.filter(scenario=scenario)
    if risk_level:
        qs = qs.filter(risk_level=risk_level)
    if year:
        try:
            qs = qs.filter(year=int(year))
        except ValueError:
            pass

    context = {
        'models':       qs,
        'scenarios':    CreditModel.Scenario.choices,
        'risk_levels':  CreditModel.RiskLevel.choices,
        'f_scenario':   scenario,
        'f_risk_level': risk_level,
        'f_year':       year,
    }
    return render(request, 'site/finances/credit_model.html', context)