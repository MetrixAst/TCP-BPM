import json
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render

from account.role_permissions import need_permission, PermissionEnums


def _get_period(request):
    try:
        days = int(request.GET.get('period', 30))
        days = max(7, min(days, 365))
    except (ValueError, TypeError):
        days = 30
    today = date.today()
    return today - timedelta(days=days), today, days


@need_permission(PermissionEnums.REPORTS)
def reports(request):
    from finances.models import TenantPaymentRegistry
    from tenants.models import Tenant
    from ecopark.models import EcoWork

    date_from, today, days = _get_period(request)
    current_month = today.replace(day=1)

    # ── Арендаторы ─────────────────────────────────────────────
    total_tenants = Tenant.objects.count()

    # ── Платежи текущего месяца ────────────────────────────────
    reg_month = TenantPaymentRegistry.objects.filter(period__gte=current_month)
    total_charged = reg_month.aggregate(s=Sum('charged'))['s'] or Decimal('0')
    total_paid    = reg_month.aggregate(s=Sum('paid'))['s']    or Decimal('0')
    collection_rate = round(float(total_paid / total_charged * 100), 1) if total_charged else 0

    # ── Задолженность ──────────────────────────────────────────
    overdue_qs     = TenantPaymentRegistry.objects.filter(status=TenantPaymentRegistry.Status.OVERDUE)
    overdue_count  = overdue_qs.count()
    overdue_amount = overdue_qs.aggregate(s=Sum('balance'))['s'] or Decimal('0')

    # ── Заявки (ServiceRequest) ────────────────────────────────
    tickets_open = tickets_total = 0
    tickets_by_status = []
    try:
        from tickets.models import ServiceRequest
        tickets_period = ServiceRequest.objects.filter(created_at__date__gte=date_from)
        tickets_total = tickets_period.count()
        tickets_open = tickets_period.filter(
            status__in=['new', 'accepted', 'in_progress']
        ).count()
        tickets_by_status = list(
            tickets_period.values('status').annotate(cnt=Count('id')).order_by('-cnt')[:6]
        )
    except Exception:
        tickets_by_status = []

    # ── Эксплуатация ──────────────────────────────────────────
    eco_total = eco_done = eco_pending = 0
    eco_amount = Decimal('0')
    eco_by_status = []
    try:
        eco_qs        = EcoWork.objects.filter(date__gte=date_from)
        eco_total     = eco_qs.count()
        eco_done      = eco_qs.filter(status='done').count()
        eco_pending   = eco_qs.filter(status__in=['pending', 'progress']).count()
        eco_amount    = eco_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
        eco_by_status = list(
            eco_qs.values('status').annotate(cnt=Count('id')).order_by('-cnt')
        )
    except Exception:
        pass

    # ── Сотрудники ─────────────────────────────────────────────
    employees_total = 0
    try:
        from account.models import Employee
        employees_total = Employee.objects.filter(status='active').count()
    except Exception:
        pass

    # ── KPI карточки ───────────────────────────────────────────
    kpi_cards = [
        {
            'label': 'Начислено (тек. месяц)',
            'value': f'{total_charged:,.0f} ₸',
            'icon': 'bi-cash-stack',
            'color': 'blue',
            'sub': f'Оплачено: {total_paid:,.0f} ₸',
            'sub_color': 'green' if collection_rate >= 80 else 'orange',
        },
        {
            'label': 'Сбор платежей',
            'value': f'{collection_rate}%',
            'icon': 'bi-percent',
            'color': 'green' if collection_rate >= 80 else 'orange',
            'sub': 'За текущий месяц',
            'sub_color': 'neutral',
        },
        {
            'label': 'Задолженность',
            'value': f'{overdue_amount:,.0f} ₸',
            'icon': 'bi-exclamation-triangle',
            'color': 'red' if overdue_count > 0 else 'green',
            'sub': f'{overdue_count} арендаторов просрочили',
            'sub_color': 'red' if overdue_count > 0 else 'green',
        },
        {
            'label': 'Арендаторы',
            'value': str(total_tenants),
            'icon': 'bi-shop',
            'color': 'purple',
            'sub': f'Сотрудников: {employees_total}',
            'sub_color': 'neutral',
        },
        {
            'label': 'Заявки (открытые)',
            'value': str(tickets_open),
            'icon': 'bi-ticket',
            'color': 'orange' if tickets_open > 5 else 'teal',
            'sub': f'За {days} дней: {tickets_total} всего',
            'sub_color': 'neutral',
        },
        {
            'label': 'Эксплуатация',
            'value': str(eco_total),
            'icon': 'bi-tools',
            'color': 'teal',
            'sub': f'Выполнено: {eco_done}, в работе: {eco_pending}',
            'sub_color': 'neutral',
        },
    ]

    # ── График: динамика платежей (последние 6 месяцев) ────────
    payment_dynamics = list(
        TenantPaymentRegistry.objects
        .annotate(month=TruncMonth('period'))
        .values('month')
        .annotate(charged=Sum('charged'), paid=Sum('paid'))
        .order_by('month')
    )
    last_6 = payment_dynamics[-6:] if len(payment_dynamics) >= 6 else payment_dynamics
    chart_payments = {
        'labels':  [r['month'].strftime('%b %Y') for r in last_6],
        'charged': [float(r['charged'] or 0) for r in last_6],
        'paid':    [float(r['paid'] or 0) for r in last_6],
    }

    # ── График: заявки по месяцам ──────────────────────────────
    chart_tickets = {'labels': [], 'counts': []}
    try:
        from tickets.models import ServiceRequest
        tickets_dynamics = list(
            ServiceRequest.objects
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(cnt=Count('id'))
            .order_by('month')
        )
        last_6t = tickets_dynamics[-6:] if len(tickets_dynamics) >= 6 else tickets_dynamics
        chart_tickets = {
            'labels': [r['month'].strftime('%b %Y') for r in last_6t],
            'counts': [r['cnt'] for r in last_6t],
        }
    except Exception:
        pass

    # ── Топ должников ──────────────────────────────────────────
    top_debtors = list(
        TenantPaymentRegistry.objects
        .filter(status=TenantPaymentRegistry.Status.OVERDUE)
        .values('tenant__name')
        .annotate(debt=Sum('balance'))
        .order_by('-debt')[:5]
    )

    # ── Лейблы статусов ───────────────────────────────────────
    TICKET_STATUS = {
        'new':         'Новая',
        'accepted':    'Принята',
        'in_progress': 'В работе',
        'done':        'Выполнена',
        'rejected':    'Отклонена',
    }
    ECO_STATUS = {
        'pending':     'Ожидает',
        'in_progress': 'В работе',
        'progress':    'В работе',
        'done':        'Выполнено',
        'cancelled':   'Отменено',
        'overdue':     'Просрочено',
    }

    context = {
        'kpi_cards':   kpi_cards,
        'period_days': days,
        'date_from':   date_from,
        'today':       today,

        'chart_payments_json': json.dumps(chart_payments, ensure_ascii=False),
        'chart_tickets_json':  json.dumps(chart_tickets,  ensure_ascii=False),

        'top_debtors': top_debtors,
        'tickets_status_rows': [
            {'status': TICKET_STATUS.get(r['status'], r['status']), 'count': r['cnt']}
            for r in tickets_by_status
        ],
        'eco_status_rows': [
            {'status': ECO_STATUS.get(r['status'], r['status']), 'count': r['cnt']}
            for r in eco_by_status
        ],

        'eco_amount':      eco_amount,
        'employees_total': employees_total,
        'total_tenants':   total_tenants,
        'collection_rate': collection_rate,
        'overdue_count':   overdue_count,
    }
    return render(request, 'site/dashboard/statistic.html', context)