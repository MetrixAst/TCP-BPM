"""Демо-данные для финансового блока.

    python manage.py seed_finance_demo           # пересоздать демо-данные
    python manage.py seed_finance_demo --clear   # только удалить демо-данные

Все демо-записи помечены (префикс DEMO-, код demo-, примечание DEMO),
поэтому повторный запуск и очистка не трогают реальные данные из 1С.
"""
import random
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from finances.models import (
    BudgetCategory, BudgetItem, CashFlowRecord, CreditModel, ExchangeRate, FinanceItem,
    FinancialStatement, GeneratedInvoice, GeneratedInvoiceItem, PaymentCalendarEntry,
    TenantPaymentRegistry,
)
from tenants.models import Tenant

MARK = 'DEMO'

DEMO_TENANTS = [
    ('Демо: Magnum Cash&Carry', 1200, 4500),
    ('Демо: Kinopark 6', 900, 3800),
    ('Демо: Технодом', 650, 6200),
    ('Демо: LC Waikiki', 480, 7100),
    ('Демо: Starbucks', 120, 11000),
    ('Демо: Marwin', 210, 6800),
    ('Демо: Аптека Europharma', 85, 9500),
    ('Демо: Фуд-корт «Казан»', 160, 8700),
]

INCOME_CATEGORIES = [
    ('demo-inc-rent', 'Арендная плата', Decimal('0.78')),
    ('demo-inc-utilities', 'Возмещение коммунальных услуг', Decimal('0.12')),
    ('demo-inc-ads', 'Реклама и промо-места', Decimal('0.06')),
    ('demo-inc-parking', 'Парковка', Decimal('0.04')),
]
EXPENSE_CATEGORIES = [
    ('demo-exp-payroll', 'Фонд оплаты труда', Decimal('0.30')),
    ('demo-exp-utilities', 'Коммунальные услуги', Decimal('0.22')),
    ('demo-exp-security', 'Охрана', Decimal('0.10')),
    ('demo-exp-cleaning', 'Клининг', Decimal('0.08')),
    ('demo-exp-repair', 'Ремонт и обслуживание', Decimal('0.12')),
    ('demo-exp-marketing', 'Маркетинг', Decimal('0.07')),
    ('demo-exp-taxes', 'Налоги', Decimal('0.11')),
]

CASH_OUTFLOWS = [
    ('demo-exp-payroll', 'Заработная плата сотрудникам', 'operating'),
    ('demo-exp-utilities', 'Оплата электроэнергии, АО «Шыгысэнерготрейд»', 'operating'),
    ('demo-exp-utilities', 'Оплата водоснабжения, ГКП «Өскемен Водоканал»', 'operating'),
    ('demo-exp-security', 'Охранные услуги, ТОО «Барыс Секьюрити»', 'operating'),
    ('demo-exp-cleaning', 'Клининговые услуги, ТОО «Таза Үй»', 'operating'),
    ('demo-exp-repair', 'Обслуживание эскалаторов, ТОО «Лифт-Сервис»', 'operating'),
    ('demo-exp-marketing', 'Рекламная кампания в 2ГИС и Instagram', 'operating'),
    ('demo-exp-taxes', 'Налог на имущество', 'operating'),
]


def q(value):
    return Decimal(value).quantize(Decimal('0.01'))


def month_start(d, shift=0):
    y, m = d.year, d.month + shift
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


class Command(BaseCommand):
    help = 'Заполняет финансовый блок демо-данными (или удаляет их с --clear).'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Только удалить демо-данные')
        parser.add_argument('--seed', type=int, default=2026)

    @transaction.atomic
    def handle(self, *args, **options):
        self.clear()
        if options['clear']:
            self.stdout.write(self.style.SUCCESS('Демо-данные финансов удалены.'))
            return

        self.rnd = random.Random(options['seed'])
        self.today = date.today()

        tenants = self.tenants()
        income, expense = self.categories()
        self.budget(income, expense)
        statements = self.statements()
        self.registry(tenants)
        self.calendar(tenants)
        self.invoices(tenants)
        self.cashflow(tenants, expense)
        self.credit_models(statements)
        self.exchange_rates()
        self.calendar_events()

        self.stdout.write(self.style.SUCCESS(
            f'Готово: арендаторов {len(tenants)}, '
            f'реестр {TenantPaymentRegistry.objects.filter(contract_number__startswith=MARK).count()}, '
            f'календарь {PaymentCalendarEntry.objects.filter(contract_number__startswith=MARK).count()}, '
            f'счета {GeneratedInvoice.objects.filter(number__startswith=MARK).count()}, '
            f'ДДС {CashFlowRecord.objects.filter(document_number__startswith=MARK).count()}, '
            f'бюджет {BudgetItem.objects.filter(category__code__startswith="demo-").count()}, '
            f'ОПиУ {FinancialStatement.objects.filter(note=MARK).count()}.'
        ))

    # ── очистка ────────────────────────────────────────────────────────
    def clear(self):
        GeneratedInvoice.objects.filter(number__startswith=MARK).delete()
        TenantPaymentRegistry.objects.filter(contract_number__startswith=MARK).delete()
        PaymentCalendarEntry.objects.filter(contract_number__startswith=MARK).delete()
        CashFlowRecord.objects.filter(document_number__startswith=MARK).delete()
        CreditModel.objects.filter(name__startswith='Демо').delete()
        FinancialStatement.objects.filter(note=MARK).delete()
        BudgetItem.objects.filter(category__code__startswith='demo-').delete()
        BudgetCategory.objects.filter(code__startswith='demo-', parent__isnull=False).delete()
        BudgetCategory.objects.filter(code__startswith='demo-').delete()
        ExchangeRate.objects.filter(source='demo').delete()
        FinanceItem.objects.filter(title__startswith='[Демо]').delete()
        Tenant.objects.filter(note=MARK).delete()

    # ── арендаторы ─────────────────────────────────────────────────────
    def tenants(self):
        result = []
        for idx, tenant in enumerate(Tenant.objects.filter(is_active=True).order_by('pk')[:12], start=1):
            rent = q((tenant.area or 0) * (tenant.price or 0)) or q(self.rnd.randint(400, 3500) * 1000)
            result.append((tenant, f'{MARK}-{tenant.pk:04d}', rent))
        if len(result) >= 6:
            return result

        start = month_start(self.today, -18)
        for name, area, price in DEMO_TENANTS[: 8 - len(result)]:
            tenant = Tenant.objects.create(
                name=name, area=area, price=price, phone='+7 700 000 00 00',
                email='demo@example.com', address='г. Усть-Каменогорск', contact='Демо-контакт',
                start_date=start, end_date=date(self.today.year + 2, 12, 31), note=MARK,
            )
            result.append((tenant, f'{MARK}-{tenant.pk:04d}', q(area * price)))
        return result

    # ── бюджет ─────────────────────────────────────────────────────────
    def categories(self):
        income_root = BudgetCategory.objects.create(
            name='Доходы ТРЦ', category_type='income', code='demo-income', order=1,
        )
        expense_root = BudgetCategory.objects.create(
            name='Расходы ТРЦ', category_type='expense', code='demo-expense', order=2,
        )
        income = [
            (BudgetCategory.objects.create(
                name=name, category_type='income', code=code, parent=income_root, order=i,
            ), share)
            for i, (code, name, share) in enumerate(INCOME_CATEGORIES, start=1)
        ]
        expense = [
            (BudgetCategory.objects.create(
                name=name, category_type='expense', code=code, parent=expense_root, order=i,
            ), share)
            for i, (code, name, share) in enumerate(EXPENSE_CATEGORIES, start=1)
        ]
        return income, expense

    def monthly_revenue(self, year, month):
        base = Decimal('68000000')
        season = Decimal(str(1 + 0.08 * ((month in (11, 12)) - (month in (1, 2)))))
        growth = Decimal(str(1 + 0.004 * ((year - 2025) * 12 + month)))
        return q(base * season * growth)

    def budget(self, income, expense):
        year = self.today.year
        for month in range(1, 13):
            revenue = self.monthly_revenue(year, month)
            past = month < self.today.month
            current = month == self.today.month
            for cats, total in ((income, revenue), (expense, revenue * Decimal('0.62'))):
                for category, share in cats:
                    plan = q(total * share)
                    deviation = Decimal(str(self.rnd.uniform(-0.09, 0.07)))
                    fact = q(plan * (1 + deviation)) if past else (
                        q(plan * Decimal(self.today.day) / monthrange(year, month)[1]) if current else Decimal('0')
                    )
                    BudgetItem.objects.create(
                        category=category, period_type='monthly', year=year, month=month,
                        plan=plan, fact=fact, forecast=fact if past else plan,
                    )

    # ── ОПиУ ───────────────────────────────────────────────────────────
    def statements(self):
        year = self.today.year
        statements = []
        quarters = {}
        for month in range(1, 13):
            revenue_plan = self.monthly_revenue(year, month)
            done = month < self.today.month
            revenue_fact = q(revenue_plan * Decimal(str(self.rnd.uniform(0.93, 1.06)))) if done else Decimal('0')
            row = dict(
                revenue_plan=revenue_plan,
                revenue_fact=revenue_fact,
                revenue_forecast=revenue_fact or revenue_plan,
                ebitda_plan=q(revenue_plan * Decimal('0.41')),
                ebitda_fact=q(revenue_fact * Decimal(str(self.rnd.uniform(0.36, 0.44)))),
                operating_profit_plan=q(revenue_plan * Decimal('0.33')),
                operating_profit_fact=q(revenue_fact * Decimal(str(self.rnd.uniform(0.29, 0.36)))),
                net_profit_plan=q(revenue_plan * Decimal('0.24')),
                net_profit_fact=q(revenue_fact * Decimal(str(self.rnd.uniform(0.2, 0.27)))),
            )
            row['ebitda_forecast'] = row['ebitda_fact'] or row['ebitda_plan']
            row['net_profit_forecast'] = row['net_profit_fact'] or row['net_profit_plan']
            statements.append(FinancialStatement.objects.create(
                period_type='monthly', year=year, month=month, note=MARK, **row,
            ))
            quarter = quarters.setdefault((month - 1) // 3 + 1, {k: Decimal('0') for k in row})
            for key, value in row.items():
                quarter[key] += value

        for quarter, row in quarters.items():
            FinancialStatement.objects.create(
                period_type='quarterly', year=year, quarter=quarter, note=MARK, **row,
            )
        FinancialStatement.objects.create(
            period_type='yearly', year=year, note=MARK,
            **{key: sum(r[key] for r in quarters.values()) for key in next(iter(quarters.values()))},
        )
        return statements

    # ── реестр оплат и календарь ───────────────────────────────────────
    def registry(self, tenants):
        for idx, (tenant, contract, rent) in enumerate(tenants):
            for shift in range(-11, 1):
                period = month_start(self.today, shift)
                planned = period.replace(day=10)
                if shift < -1 or (shift == -1 and idx % 4):
                    status, paid, actual = 'paid', rent, planned - timedelta(days=self.rnd.randint(0, 4))
                elif shift == -1:
                    status, paid, actual = 'overdue', q(rent * Decimal('0.3')), None
                elif planned <= self.today:
                    status, paid, actual = (
                        ('paid', rent, planned) if idx % 3 else ('partial', q(rent * Decimal('0.5')), planned)
                    )
                else:
                    status, paid, actual = 'pending', Decimal('0'), None
                if idx == 1 and shift in (-2, -1):
                    status, paid, actual = 'overdue', Decimal('0'), None
                overdue_days = (self.today - planned).days if status == 'overdue' else 0
                TenantPaymentRegistry.objects.create(
                    tenant=tenant, contract_number=contract, period=period, charged=rent, paid=paid,
                    planned_date=planned, actual_date=actual, overdue_days=overdue_days, status=status,
                )

    def calendar(self, tenants):
        for idx, (tenant, contract, rent) in enumerate(tenants):
            for shift in range(-3, 3):
                expected = month_start(self.today, shift).replace(day=5 + idx % 20)
                if expected < self.today and not (idx == 1 and shift == -1):
                    status = 'fact'
                    actual_amount = rent if idx % 5 else q(rent * Decimal('0.8'))
                    actual_date = expected + timedelta(days=self.rnd.randint(-2, 3))
                elif expected < self.today:
                    status, actual_amount, actual_date = 'overdue', Decimal('0'), None
                else:
                    status, actual_amount, actual_date = 'plan', Decimal('0'), None
                PaymentCalendarEntry.objects.create(
                    tenant=tenant, contract_number=contract, expected_date=expected,
                    expected_amount=rent, actual_amount=actual_amount, actual_date=actual_date,
                    status=status,
                )

    # ── счета ──────────────────────────────────────────────────────────
    def invoices(self, tenants):
        number = 1
        for idx, (tenant, contract, rent) in enumerate(tenants):
            for shift, status in ((-1, 'paid'), (0, ('sent', 'viewed', 'created', 'paid')[idx % 4])):
                period = month_start(self.today, shift)
                invoice = GeneratedInvoice.objects.create(
                    tenant=tenant, number=f'{MARK}-{period:%y%m}-{number:03d}', period=period,
                    contract_number=contract, status=status,
                    sent_via='email' if status != 'created' else None,
                    comment='Демо-счёт',
                )
                number += 1
                utilities = q(rent * Decimal('0.14'))
                lines = [
                    (f'Аренда помещения за {period:%m.%Y}', rent),
                    ('Возмещение коммунальных услуг', utilities),
                ]
                total = vat = Decimal('0')
                for name, price in lines:
                    item = GeneratedInvoiceItem.objects.create(
                        invoice=invoice, name=name, quantity=1, unit='мес.', price=price,
                    )
                    total += item.total
                    vat += item.vat_amount
                invoice.total_amount = total + vat
                invoice.vat_amount = vat
                invoice.save(update_fields=['total_amount', 'vat_amount'])

    # ── ДДС ────────────────────────────────────────────────────────────
    def cashflow(self, tenants, expense):
        categories = {category.code: category for category, _ in expense}
        number = 1

        def add(direction, amount, day, description, flow='operating', category=None):
            nonlocal number
            CashFlowRecord.objects.create(
                direction=direction, flow_type=flow, amount=q(amount), transaction_date=day,
                value_date=day, description=description, budget_category=category,
                document_number=f'{MARK}-PP-{number:05d}', bank_account='KZ12 601A 0000 0000 0001',
            )
            number += 1

        for days_ago in range(120, -1, -1):
            day = self.today - timedelta(days=days_ago)
            if day.weekday() >= 5:
                continue
            for tenant, _, rent in tenants:
                if day.day == 5 + tenant.pk % 20:
                    add('inflow', rent, day, f'Оплата аренды, {tenant.name}')
            if self.rnd.random() < 0.6:
                add('inflow', self.rnd.randint(150, 900) * 1000, day, 'Поступления от парковки')
            code, description, flow = self.rnd.choice(CASH_OUTFLOWS)
            add('outflow', self.rnd.randint(800, 6500) * 1000, day, description, flow, categories[code])
            if day.day in (10, 25):
                add('outflow', 9_800_000, day, 'Заработная плата сотрудникам', category=categories['demo-exp-payroll'])
            if day.day == 15:
                add('outflow', 6_400_000, day, 'Погашение кредита, АО «Халык Банк»', 'financing')
            if day.day == 20 and day.month % 2:
                add('outflow', 14_500_000, day, 'Модернизация системы кондиционирования', 'investing')

    # ── кредитная модель ───────────────────────────────────────────────
    def credit_models(self, statements):
        year = self.today.year + 1
        months = [f'{year}-{m:02d}' for m in range(1, 13)]
        for scenario, factor in (('base', 1.0), ('optimistic', 1.12), ('pessimistic', 0.82)):
            income = {m: round(72_000_000 * factor * (1 + i * 0.005), 2) for i, m in enumerate(months)}
            expenses = {m: round(44_000_000 * (1 + i * 0.004), 2) for i, m in enumerate(months)}
            model = CreditModel(
                name='Демо: Реконструкция фуд-корта', scenario=scenario, year=year,
                description='Кредит на реконструкцию фуд-корта и расширение парковки.',
                loan_amount=Decimal('1500000000'), loan_rate=Decimal('16.5'), loan_term_months=60,
                annual_debt_service=Decimal('0'), forecast_pnl={}, forecast_cashflow={},
                projected_income=income, projected_expenses=expenses,
                financial_statement=statements[-1] if statements else None,
                period_start=date(year, 1, 1), period_end=date(year, 12, 31),
            )
            model.calculate_dscr()
            model.projected_cashflow = {m: round(income[m] - expenses[m], 2) for m in months}
            model.save()

    def exchange_rates(self):
        base = {'USD': 512.4, 'EUR': 556.8, 'RUB': 5.62, 'CNY': 70.9}
        for days_ago in range(30, -1, -1):
            day = self.today - timedelta(days=days_ago)
            for currency, rate in base.items():
                ExchangeRate.objects.update_or_create(
                    currency=currency, date=day,
                    defaults={'rate': round(rate * (1 + self.rnd.uniform(-0.01, 0.01)), 4), 'source': 'demo'},
                )

    def calendar_events(self):
        from finances.enums import FinanceItemType
        types = [slug for slug, _ in FinanceItemType.list()]
        titles = [
            'Сверка с арендаторами', 'Оплата налогов', 'Отчёт для банка', 'Бюджетный комитет',
            'Закрытие месяца в 1С', 'Инвентаризация',
        ]
        for i, title in enumerate(titles):
            FinanceItem.objects.create(
                title=f'[Демо] {title}', date=self.today + timedelta(days=i * 4 - 6),
                category=types[i % len(types)], text='Демо-событие финансового календаря',
            )
