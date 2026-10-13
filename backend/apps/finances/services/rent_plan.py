"""
План поступлений аренды по договорам (ТЗ 4.4: «план — из договоров и графиков»).

Для каждого действующего арендатора на N месяцев вперёд считается ожидаемое
начисление: площадь × ставка за м², со скидкой до даты её окончания и в
пределах срока аренды. Запись создаётся в календаре платежей со статусом
«План». Как только по арендатору за этот месяц приходит реальный счёт из 1С,
плановая запись удаляется — дальше календарь показывает счёт.

Процент с оборота и индексация ставки не учитываются: данных об обороте и
шаге повышения в карточке арендатора нет.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from finances.models import PaymentCalendarEntry

PLAN_CONTRACT = 'План по договору'


def plan_key(tenant_id: int, month: date) -> str:
    return f'plan:{tenant_id}:{month:%Y-%m}'


def _months(start: date, count: int):
    year, month = start.year, start.month
    for _ in range(count):
        yield date(year, month, 1)
        month += 1
        if month == 13:
            year, month = year + 1, 1


def monthly_rent(tenant, month: date) -> Decimal:
    amount = Decimal(str(tenant.area or 0)) * Decimal(str(tenant.price or 0))
    discount_active = tenant.discount and (not tenant.discount_date or tenant.discount_date >= month)
    if discount_active:
        amount = amount * (Decimal(100) - Decimal(tenant.discount)) / Decimal(100)
    return amount.quantize(Decimal('0.01'))


def _in_lease(tenant, month: date) -> bool:
    month_end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    if tenant.start_date and tenant.start_date > month_end:
        return False
    if tenant.end_date and tenant.end_date < month:
        return False
    return True


def _has_invoice(tenant_id: int, month: date) -> bool:
    return PaymentCalendarEntry.objects.filter(
        tenant_id=tenant_id,
        onec_id__startswith='inv:',
        expected_date__year=month.year,
        expected_date__month=month.month,
    ).exists()


@transaction.atomic
def generate_rent_plan(months_ahead: int | None = None, today: date | None = None) -> dict:
    from tenants.models import Tenant

    today = today or timezone.localdate()
    months_ahead = months_ahead or getattr(settings, 'RENT_PLAN_MONTHS', 6)
    due_day = getattr(settings, 'RENT_DUE_DAY', 10)
    months = list(_months(today.replace(day=1), months_ahead))

    keep = set()
    created = updated = 0
    for tenant in Tenant.objects.filter(is_active=True, area__gt=0, price__gt=0):
        for month in months:
            if not _in_lease(tenant, month) or _has_invoice(tenant.pk, month):
                continue
            amount = monthly_rent(tenant, month)
            if amount <= 0:
                continue
            expected = month.replace(day=min(due_day, calendar.monthrange(month.year, month.month)[1]))
            key = plan_key(tenant.pk, month)
            keep.add(key)
            _entry, was_created = PaymentCalendarEntry.objects.update_or_create(
                onec_id=key,
                defaults={
                    'tenant': tenant,
                    'contract_number': PLAN_CONTRACT,
                    'expected_date': expected,
                    'expected_amount': amount,
                    'status': (
                        PaymentCalendarEntry.Status.OVERDUE if expected < today
                        else PaymentCalendarEntry.Status.PLAN
                    ),
                },
            )
            created += was_created
            updated += not was_created

    # Плановые записи, которые больше не нужны: пришёл счёт, договор закончился,
    # арендатор в архиве или изменились условия.
    stale = PaymentCalendarEntry.objects.filter(
        onec_id__startswith='plan:', expected_date__gte=months[0],
    ).exclude(onec_id__in=keep)
    removed = stale.count()
    stale.delete()
    return {'created': created, 'updated': updated, 'removed': removed}


def drop_plan_for_invoice(tenant_id: int, month: date) -> None:
    PaymentCalendarEntry.objects.filter(onec_id=plan_key(tenant_id, month)).delete()
