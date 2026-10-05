"""
Мок-данные для блока Финансы + телефоны в сервисе счетов (WhatsApp).

  python manage.py seed_finances_demo
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from finances.models import (
    BudgetCategory,
    BudgetItem,
    CashFlowRecord,
    FinancialStatement,
    GeneratedInvoice,
    GeneratedInvoiceItem,
    PaymentCalendarEntry,
    TenantPaymentRegistry,
)
from onec.models import Counterparty
from tenants.models import Tenant, TenantCategory


MOCK_COUNTERPARTIES = [
    {
        'id_1c': 'bpm-demo-romashka',
        'short_name': 'ТОО Ромашка',
        'full_name': 'Товарищество с ограниченной ответственностью «Ромашка»',
        'bin_number': '990940012345',
        'phone': '+77015550101',
        'email': 'finance@romashka.kz',
        'tenant_name': 'Ромашка Café',
    },
    {
        'id_1c': 'bpm-demo-puma',
        'short_name': 'West Sport (PUMA)',
        'full_name': 'ТОО West Sport Alliance KZ',
        'bin_number': '990840014089',
        'phone': '+77017654321',
        'email': 'arenda@puma-kz.example',
        'tenant_name': 'PUMA',
    },
    {
        'id_1c': 'bpm-demo-lcw',
        'short_name': 'TEMA RETAIL (LCW)',
        'full_name': 'ТОО TEMA RETAIL KZ',
        'bin_number': '990640002890',
        'phone': '+77021112233',
        'email': 'billing@lcw.example',
        'tenant_name': 'LCW',
    },
    {
        'id_1c': 'bpm-demo-kfc',
        'short_name': 'KFC Astana',
        'full_name': 'ТОО Food Service Kazakhstan',
        'bin_number': '990540001111',
        'phone': '+77072223344',
        'email': 'kz-finance@kfc.example',
        'tenant_name': 'KFC',
    },
    {
        'id_1c': 'bpm-demo-sinsay',
        'short_name': 'Sinsay',
        'full_name': 'ТОО Fashion Retail KZ',
        'bin_number': '990140009999',
        'phone': '+77083334455',
        'email': 'arenda@sinsay.example',
        'tenant_name': 'Sinsay',
    },
]


class Command(BaseCommand):
    help = 'Заполняет Финансы мок-данными и регистрирует телефоны в сервисе счетов'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-invoice-service',
            action='store_true',
            help='Не писать телефоны в invoice API',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = date.today()
        period = today.replace(day=1)
        prev_period = (period - timedelta(days=1)).replace(day=1)

        category, _ = TenantCategory.objects.get_or_create(title='Ритейл (демо)')
        partners = []

        for row in MOCK_COUNTERPARTIES:
            cp, _ = Counterparty.objects.update_or_create(
                id_1c=row['id_1c'],
                defaults={
                    'short_name': row['short_name'],
                    'full_name': row['full_name'],
                    'bin_number': row['bin_number'],
                    'phone': row['phone'],
                    'email': row['email'],
                    'is_customer': True,
                    'address': 'г. Астана, пр. Туран 37',
                },
            )
            tenant = Tenant.objects.filter(name=row['tenant_name']).first()
            if tenant is None:
                tenant = Tenant.objects.create(
                    name=row['tenant_name'],
                    category=category,
                    area=85.0,
                    price=12000.0,
                    phone=row['phone'],
                    email=row['email'],
                    address='TRC BPM Demo',
                    contact='Менеджер аренды',
                    start_date=today - timedelta(days=180),
                    end_date=today + timedelta(days=540),
                )
            else:
                tenant.phone = row['phone']
                tenant.email = row['email']
                if tenant.category_id is None:
                    tenant.category = category
                tenant.save(update_fields=['phone', 'email', 'category'])
            partners.append((cp, tenant, row))

        self.stdout.write(self.style.SUCCESS(f'Контрагенты/арендаторы: {len(partners)}'))

        # Keep legacy WA id in sync with service tenant phones
        legacy, _ = Counterparty.objects.update_or_create(
            id_1c='bpm-local-cp-001',
            defaults={
                'short_name': 'ТОО Ромашка (local)',
                'full_name': 'ТОО Ромашка local WA',
                'phone': '+77015550101',
                'email': 'wa@romashka.kz',
                'is_customer': True,
                'bin_number': '120940099001',
            },
        )

        created_invoices = 0
        specs = [
            # (suffix, status, sent_via, days_ago, amount, partner_idx)
            ('Аренда-01', GeneratedInvoice.Status.CREATED, None, 0, '450000.00', 0),
            ('Аренда-02', GeneratedInvoice.Status.CREATED, None, 1, '380000.00', 1),
            ('КУ-01', GeneratedInvoice.Status.CREATED, None, 0, '125000.00', 2),
            ('Аренда-03', GeneratedInvoice.Status.SENT, GeneratedInvoice.SentVia.WHATSAPP, 2, '510000.00', 0),
            ('Аренда-04', GeneratedInvoice.Status.SENT, GeneratedInvoice.SentVia.EMAIL, 3, '290000.00', 3),
            ('КУ-02', GeneratedInvoice.Status.VIEWED, GeneratedInvoice.SentVia.WHATSAPP, 5, '98000.00', 4),
            ('Аренда-05', GeneratedInvoice.Status.PAID, GeneratedInvoice.SentVia.EMAIL, 12, '620000.00', 1),
            ('Аренда-06', GeneratedInvoice.Status.PAID, GeneratedInvoice.SentVia.WHATSAPP, 20, '415000.00', 2),
            ('Аренда-07', GeneratedInvoice.Status.CANCELLED, None, 8, '200000.00', 3),
            ('Маркетинг-01', GeneratedInvoice.Status.SENT, GeneratedInvoice.SentVia.MANUAL, 4, '75000.00', 4),
        ]

        for suffix, status, sent_via, days_ago, amount, idx in specs:
            cp, tenant, _ = partners[idx]
            number = f'DEMO-{period.strftime("%Y%m")}-{suffix}'
            onec_id = f'demo-inv-{suffix.lower()}'
            inv, was_created = GeneratedInvoice.objects.update_or_create(
                onec_id=onec_id,
                defaults={
                    'number': number,
                    'tenant': tenant,
                    'counterparty': cp,
                    'period': period if days_ago < 15 else prev_period,
                    'contract_number': f'Demo-{tenant.pk:03d}',
                    'total_amount': Decimal(amount),
                    'vat_amount': (Decimal(amount) * Decimal('0.12')).quantize(Decimal('0.01')),
                    'comment': 'Демо-счёт для проверки блока Финансы',
                    'status': status,
                    'sent_via': sent_via,
                    'sent_at': timezone.now() - timedelta(days=days_ago) if sent_via else None,
                },
            )
            if was_created or not inv.items.exists():
                inv.items.all().delete()
                qty = Decimal('1')
                price = Decimal(amount)
                item = GeneratedInvoiceItem(
                    invoice=inv,
                    name='Аренда / КУ (демо)' if 'КУ' in suffix else 'Аренда помещения (демо)',
                    quantity=qty,
                    unit='мес',
                    price=price,
                    vat_rate=Decimal('12'),
                )
                item.save()
                created_invoices += 1

        # Extra ready-to-send invoice on legacy WA counterparty
        GeneratedInvoice.objects.update_or_create(
            onec_id='demo-inv-wa-ready',
            defaults={
                'number': f'DEMO-{period.strftime("%Y%m")}-WA-READY',
                'tenant': partners[0][1],
                'counterparty': legacy,
                'period': period,
                'contract_number': 'Demo-WA-001',
                'total_amount': Decimal('150000.00'),
                'vat_amount': Decimal('18000.00'),
                'comment': 'Готов к отправке WhatsApp',
                'status': GeneratedInvoice.Status.CREATED,
                'sent_via': None,
                'sent_at': None,
            },
        )
        wa_inv = GeneratedInvoice.objects.get(onec_id='demo-inv-wa-ready')
        if not wa_inv.items.exists():
            GeneratedInvoiceItem(
                invoice=wa_inv,
                name='Аренда (тест WhatsApp)',
                quantity=Decimal('1'),
                unit='мес',
                price=Decimal('150000.00'),
                vat_rate=Decimal('12'),
            ).save()

        self.stdout.write(self.style.SUCCESS(
            f'Счета: {GeneratedInvoice.objects.filter(onec_id__startswith="demo-inv-").count()} демо'
        ))

        # Payment registry + calendar
        reg_n = cal_n = 0
        for i, (cp, tenant, row) in enumerate(partners):
            for p_i, p_date in enumerate((prev_period, period)):
                charged = Decimal('400000.00') + Decimal(i * 25000)
                paid = charged if p_i == 0 else (Decimal('0') if i % 2 else charged / 2)
                status = (
                    TenantPaymentRegistry.Status.PAID if paid == charged
                    else TenantPaymentRegistry.Status.PARTIAL if paid > 0
                    else TenantPaymentRegistry.Status.OVERDUE if p_date < period
                    else TenantPaymentRegistry.Status.PENDING
                )
                TenantPaymentRegistry.objects.update_or_create(
                    tenant=tenant,
                    contract_number=f'Demo-{tenant.pk:03d}',
                    period=p_date,
                    defaults={
                        'charged': charged,
                        'paid': paid,
                        'balance': charged - paid,
                        'planned_date': p_date + timedelta(days=10),
                        'actual_date': p_date + timedelta(days=12) if paid == charged else None,
                        'overdue_days': 5 if status == TenantPaymentRegistry.Status.OVERDUE else 0,
                        'status': status,
                        'onec_id': f'demo-reg-{tenant.pk}-{p_date.strftime("%Y%m")}',
                    },
                )
                reg_n += 1

                expected = p_date + timedelta(days=10)
                cal_status = (
                    PaymentCalendarEntry.Status.FACT if paid == charged
                    else PaymentCalendarEntry.Status.OVERDUE if expected < today and paid < charged
                    else PaymentCalendarEntry.Status.PLAN
                )
                PaymentCalendarEntry.objects.update_or_create(
                    tenant=tenant,
                    contract_number=f'Demo-{tenant.pk:03d}',
                    expected_date=expected,
                    defaults={
                        'expected_amount': charged,
                        'actual_amount': paid,
                        'actual_date': expected + timedelta(days=2) if paid == charged else None,
                        'status': cal_status,
                        'onec_id': f'demo-cal-{tenant.pk}-{expected.isoformat()}',
                    },
                )
                cal_n += 1

        self.stdout.write(self.style.SUCCESS(f'Реестр: {reg_n}, календарь: {cal_n}'))

        # Budget + OPiU + cashflow (light)
        income, _ = BudgetCategory.objects.get_or_create(
            code='DEMO-INC-RENT',
            defaults={'name': 'Арендный доход (демо)', 'category_type': BudgetCategory.Type.INCOME, 'order': 1},
        )
        expense, _ = BudgetCategory.objects.get_or_create(
            code='DEMO-EXP-UTIL',
            defaults={'name': 'Коммунальные (демо)', 'category_type': BudgetCategory.Type.EXPENSE, 'order': 1},
        )
        for month in range(max(1, today.month - 2), today.month + 1):
            for cat, plan, fact in (
                (income, Decimal('2500000'), Decimal('2310000')),
                (expense, Decimal('480000'), Decimal('455000')),
            ):
                BudgetItem.objects.update_or_create(
                    category=cat,
                    period_type=BudgetItem.Period.MONTHLY,
                    year=today.year,
                    month=month,
                    quarter=None,
                    defaults={
                        'plan': plan,
                        'fact': fact if month < today.month else fact * Decimal('0.6'),
                        'forecast': plan,
                        'note': 'Демо',
                    },
                )

        for month in range(max(1, today.month - 2), today.month + 1):
            FinancialStatement.objects.update_or_create(
                period_type=FinancialStatement.Period.MONTHLY,
                year=today.year,
                month=month,
                quarter=None,
                defaults={
                    'revenue_plan': Decimal('2500000'),
                    'revenue_fact': Decimal('2310000') if month < today.month else Decimal('1400000'),
                    'revenue_forecast': Decimal('2450000'),
                    'ebitda_plan': Decimal('900000'),
                    'ebitda_fact': Decimal('820000') if month < today.month else Decimal('500000'),
                    'ebitda_forecast': Decimal('880000'),
                    'operating_profit_plan': Decimal('700000'),
                    'operating_profit_fact': Decimal('640000') if month < today.month else Decimal('380000'),
                    'net_profit_plan': Decimal('520000'),
                    'net_profit_fact': Decimal('470000') if month < today.month else Decimal('260000'),
                    'net_profit_forecast': Decimal('500000'),
                    'note': 'Демо ОПиУ',
                    'onec_id': f'demo-opiu-{today.year}-{month:02d}',
                },
            )

        for day_offset, amount, direction, title, partner_idx in (
            (-2, Decimal('450000'), CashFlowRecord.Direction.INFLOW, 'Оплата аренды Ромашка', 0),
            (-1, Decimal('125000'), CashFlowRecord.Direction.OUTFLOW, 'КУ поставщику', 2),
            (0, Decimal('290000'), CashFlowRecord.Direction.INFLOW, 'Оплата KFC', 3),
            (1, Decimal('80000'), CashFlowRecord.Direction.OUTFLOW, 'Маркетинг ТРЦ', 4),
            (3, Decimal('510000'), CashFlowRecord.Direction.INFLOW, 'Оплата PUMA', 1),
        ):
            d = today + timedelta(days=day_offset)
            cp = partners[partner_idx][0]
            CashFlowRecord.objects.update_or_create(
                onec_id=f'demo-cf-{d.isoformat()}-{direction}',
                defaults={
                    'transaction_date': d,
                    'amount': amount,
                    'direction': direction,
                    'flow_type': CashFlowRecord.FlowType.OPERATING,
                    'description': title,
                    'document_number': f'DEMO-CF-{d.strftime("%Y%m%d")}',
                    'counterparty': cp,
                    'budget_category': income if direction == CashFlowRecord.Direction.INFLOW else expense,
                },
            )

        self.stdout.write(self.style.SUCCESS('Бюджет / ОПиУ / ДДС заполнены'))

        if not options['skip_invoice_service']:
            n = self._sync_invoice_phones(partners + [(legacy, partners[0][1], {
                'id_1c': legacy.id_1c,
                'short_name': legacy.short_name,
                'phone': legacy.phone,
            })])
            self.stdout.write(self.style.SUCCESS(f'Телефоны в сервисе счетов: {n}'))

        # summary for UI
        ready = GeneratedInvoice.objects.filter(
            status=GeneratedInvoice.Status.CREATED,
            onec_id__startswith='demo-inv-',
        ).order_by('id')
        self.stdout.write('')
        self.stdout.write('Готовые к отправке счета:')
        for inv in ready:
            self.stdout.write(f'  /finances/invoices/{inv.pk}/  №{inv.number}  {inv.counterparty}')

    def _sync_invoice_phones(self, partners) -> int:
        base = (settings.INVOICE_SERVICE_URL or '').rstrip('/')
        trc_id = settings.INVOICE_SERVICE_TENANT_ID
        user = settings.INVOICE_SERVICE_USERNAME
        password = settings.INVOICE_SERVICE_PASSWORD
        if not all([base, trc_id, user, password]):
            self.stdout.write(self.style.WARNING('INVOICE_SERVICE_* не настроен — пропуск'))
            return 0

        try:
            login = requests.post(
                f'{base}/api/admin/auth/login',
                json={'username': user, 'password': password},
                timeout=15,
            )
            login.raise_for_status()
            token = login.json()['access_token']
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'Не удалось войти в invoice API: {exc}'))
            return 0

        headers = {'Authorization': f'Bearer {token}'}
        # Prefer TRC that matches configured tenant id; also mirror to local TRC 4 if present
        trc_ids = [int(trc_id)]
        try:
            trcs = requests.get(f'{base}/api/catalog/trcs', headers=headers, timeout=15).json()
            for t in trcs:
                if t.get('id') and t['id'] not in trc_ids and 'Local' in (t.get('name') or ''):
                    trc_ids.append(t['id'])
        except Exception:
            pass

        payloads = []
        seen = set()
        for cp, _tenant, row in partners:
            key = (row['id_1c'], row['phone'])
            if key in seen:
                continue
            seen.add(key)
            payloads.append({
                'one_c_counterparty_id': row['id_1c'],
                'phone': row['phone'],
                'counterparty_name': row.get('short_name') or cp.short_name,
            })

        count = 0
        for tid in trc_ids:
            try:
                resp = requests.put(
                    f'{base}/api/admin/trcs/{tid}/counterparty-phones',
                    headers=headers,
                    json=payloads,
                    timeout=15,
                )
                if resp.status_code < 400:
                    count += len(payloads)
                    continue
                self.stdout.write(self.style.WARNING(
                    f'bulk phones trc={tid}: {resp.status_code} {resp.text[:160]}'
                ))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'phone sync error trc={tid}: {exc}'))

            for payload in payloads:
                try:
                    resp = requests.post(
                        f'{base}/api/catalog/counterparty-phones',
                        headers=headers,
                        params={'tenant_id': tid},
                        json=payload,
                        timeout=15,
                    )
                    if resp.status_code < 400:
                        count += 1
                    else:
                        self.stdout.write(self.style.WARNING(
                            f'phone {payload["one_c_counterparty_id"]} trc={tid}: '
                            f'{resp.status_code} {resp.text[:120]}'
                        ))
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(f'phone sync error: {exc}'))
        return count
