from django.db import models
from account.models import UserAccount

from .enums import FinanceItemType

from tenants.models import Tenant
from decimal import Decimal

class FinanceItem(models.Model):

    TYPES = FinanceItemType.list()

    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Пользователь", null=True, blank=True)
    title = models.CharField("Заголовок", max_length=100)
    text = models.TextField("Комментарии", null=True, blank=True)
    date = models.DateField(verbose_name="Дата")
    category = models.SlugField("Тип", choices=TYPES)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Календарь (финансы)"
        verbose_name_plural = "Календарь (финансы)"
        ordering = ['-id']


class TenantPaymentRegistry(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PAID = 'paid', 'Оплачен'
        PARTIAL = 'partial', 'Частично оплачен'
        OVERDUE = 'overdue','Просрочен'
        CANCELLED = 'cancelled', 'Отменён'

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='payment_registry',
        verbose_name='Арендатор',
    )

    contract_number = models.CharField('Номер договора', max_length=100)
    period = models.DateField('Период (месяц/год)')   

    charged = models.DecimalField('Начислено',  max_digits=14, decimal_places=2, default=0)
    paid = models.DecimalField('Оплачено',   max_digits=14, decimal_places=2, default=0)
    balance = models.DecimalField('Задолженность', max_digits=14, decimal_places=2, default=0)

    planned_date = models.DateField('Плановая дата оплаты', null=True, blank=True)
    actual_date = models.DateField('Фактическая дата оплаты', null=True, blank=True)

    overdue_days = models.IntegerField('Дней просрочки', default=0)

    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    onec_id = models.CharField('ID в 1С', max_length=100, unique=True, null=True, blank=True)
    synced_at = models.DateTimeField('Дата синхронизации', null=True, blank=True)

    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Платёж арендатора'
        verbose_name_plural = 'Реестр платежей арендаторов'
        ordering = ['-period', 'tenant']
        unique_together = [('tenant', 'contract_number', 'period')]
        indexes               = [
            models.Index(fields=['status']),
            models.Index(fields=['period']),
            models.Index(fields=['tenant', 'period']),
        ]

    def __str__(self):
        return f"{self.tenant} | {self.period.strftime('%m.%Y')} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.onec_id:
            self.balance = self.charged - self.paid
        super().save(*args, **kwargs)


class PaymentCalendarEntry(models.Model):

    class Status(models.TextChoices):
        PLAN    = 'plan',    'План'
        FACT    = 'fact',    'Факт'
        OVERDUE = 'overdue', 'Просрочен'

    tenant          = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='payment_calendar',
        verbose_name='Арендатор',
    )
    contract_number = models.CharField('Номер договора', max_length=100)
    expected_date   = models.DateField('Плановая дата оплаты')
    expected_amount = models.DecimalField('Плановая сумма', max_digits=14, decimal_places=2, default=0)
    actual_amount   = models.DecimalField('Фактическая сумма', max_digits=14, decimal_places=2, default=0)
    actual_date     = models.DateField('Фактическая дата оплаты', null=True, blank=True)
    status          = models.CharField(
        'Статус',
        max_length=10,
        choices=Status.choices,
        default=Status.PLAN,
        db_index=True,
    )

    onec_id   = models.CharField('ID в 1С', max_length=100, unique=True, null=True, blank=True)
    synced_at = models.DateTimeField('Дата синхронизации', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Запись календаря платежей'
        verbose_name_plural = 'Календарь платежей'
        ordering            = ['expected_date', 'tenant']
        unique_together     = [('tenant', 'contract_number', 'expected_date')]
        indexes             = [
            models.Index(fields=['expected_date']),
            models.Index(fields=['status']),
            models.Index(fields=['tenant', 'expected_date']),
        ]

    def __str__(self):
        return (
            f"{self.tenant} | {self.expected_date.strftime('%d.%m.%Y')} | "
            f"{self.expected_amount} | {self.get_status_display()}"
        )

class GeneratedInvoice(models.Model):

    class Status(models.TextChoices):
        CREATED   = 'created',   'Создан'
        SENT      = 'sent',      'Отправлен'
        VIEWED    = 'viewed',    'Просмотрен'
        PAID      = 'paid',      'Оплачен'
        CANCELLED = 'cancelled', 'Отменён'

    class SentVia(models.TextChoices):
        EMAIL     = 'email',     'Email'
        WHATSAPP  = 'whatsapp',  'WhatsApp'
        TELEGRAM  = 'telegram',  'Telegram'
        MANUAL    = 'manual',    'Вручную'

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='generated_invoices',
        verbose_name='Арендатор',
        null=True, blank=True,
    )
    counterparty = models.ForeignKey(
        'onec.Counterparty',
        on_delete=models.PROTECT,
        related_name='generated_invoices',
        verbose_name='Контрагент',
        null=True, blank=True,
    )

    number          = models.CharField('Номер счёта', max_length=100)
    period          = models.DateField('Период', null=True, blank=True)
    contract_number = models.CharField('Номер договора', max_length=100, null=True, blank=True)
    total_amount    = models.DecimalField('Сумма', max_digits=14, decimal_places=2, default=0)
    vat_amount      = models.DecimalField('НДС', max_digits=14, decimal_places=2, default=0)
    comment         = models.TextField('Комментарий', null=True, blank=True)

    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        db_index=True,
    )

    sent_via = models.CharField(
        'Способ отправки',
        max_length=20,
        choices=SentVia.choices,
        null=True, blank=True,
    )
    sent_at = models.DateTimeField('Дата отправки', null=True, blank=True)

    onec_invoice_number = models.CharField(
        'Номер счёта в 1С', max_length=100, null=True, blank=True
    )
    onec_status   = models.CharField('Статус в 1С', max_length=50, null=True, blank=True)
    onec_id       = models.CharField('ID в 1С', max_length=100, unique=True, null=True, blank=True)
    synced_at     = models.DateTimeField('Дата синхронизации', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Выставленный счёт'
        verbose_name_plural = 'Выставленные счета'
        ordering            = ['-created_at']
        indexes             = [
            models.Index(fields=['status']),
            models.Index(fields=['period']),
            models.Index(fields=['tenant', 'period']),
        ]

    def __str__(self):
        counterpart = self.tenant or self.counterparty or '—'
        return f"Счёт №{self.number} | {counterpart} | {self.get_status_display()}"


class GeneratedInvoiceItem(models.Model):
    invoice  = models.ForeignKey(
        GeneratedInvoice,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Счёт',
    )
    name       = models.CharField('Наименование', max_length=255)
    quantity   = models.DecimalField('Количество', max_digits=10, decimal_places=3, default=1)
    unit       = models.CharField('Единица измерения', max_length=20, null=True, blank=True)
    price      = models.DecimalField('Цена', max_digits=14, decimal_places=2, default=0)
    total      = models.DecimalField('Итого', max_digits=14, decimal_places=2, default=0)
    vat_rate   = models.DecimalField('Ставка НДС %', max_digits=5, decimal_places=2, default=12)
    vat_amount = models.DecimalField('Сумма НДС', max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name        = 'Позиция счёта'
        verbose_name_plural = 'Позиции счёта'
        ordering            = ['id']

    def save(self, *args, **kwargs):
        self.total      = round(self.quantity * self.price, 2)
        self.vat_amount = round(self.total * self.vat_rate / 100, 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} × {self.quantity} = {self.total}"

class BudgetCategory(models.Model):

    class Type(models.TextChoices):
        INCOME  = 'income',  'Доход'
        EXPENSE = 'expense', 'Расход'

    name        = models.CharField('Название', max_length=200)
    category_type = models.CharField(
        'Тип', max_length=10, choices=Type.choices, db_index=True
    )
    parent      = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='children',
        verbose_name='Родительская категория',
    )
    code        = models.CharField('Код', max_length=50, unique=True, null=True, blank=True)
    order       = models.PositiveIntegerField('Порядок', default=0)
    is_active   = models.BooleanField('Активна', default=True)
    description = models.TextField('Описание', null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Категория бюджета'
        verbose_name_plural = 'Категории бюджета'
        ordering            = ['category_type', 'order', 'name']
        indexes             = [
            models.Index(fields=['category_type']),
            models.Index(fields=['parent']),
        ]

    def __str__(self):
        if self.parent:
            return f"{self.parent} → {self.name}"
        return self.name

    @property
    def is_root(self):
        return self.parent is None

    @property
    def level(self):
        lvl, current = 0, self
        while current.parent:
            lvl += 1
            current = current.parent
        return lvl


class BudgetItem(models.Model):

    class Period(models.TextChoices):
        MONTHLY   = 'monthly',   'Месяц'
        QUARTERLY = 'quarterly', 'Квартал'
        YEARLY    = 'yearly',    'Год'

    category    = models.ForeignKey(
        BudgetCategory,
        on_delete=models.PROTECT,
        related_name='items',
        verbose_name='Категория',
    )
    period_type = models.CharField(
        'Тип периода', max_length=10,
        choices=Period.choices,
        default=Period.MONTHLY,
    )
    year        = models.PositiveIntegerField('Год')
    month       = models.PositiveSmallIntegerField('Месяц (1-12)', null=True, blank=True)
    quarter     = models.PositiveSmallIntegerField('Квартал (1-4)', null=True, blank=True)

    plan        = models.DecimalField('План',     max_digits=16, decimal_places=2, default=0)
    fact        = models.DecimalField('Факт',     max_digits=16, decimal_places=2, default=0)
    forecast    = models.DecimalField('Прогноз',  max_digits=16, decimal_places=2, default=0)

    note        = models.TextField('Примечание', null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Строка бюджета'
        verbose_name_plural = 'Строки бюджета'
        ordering            = ['year', 'month', 'quarter', 'category']
        unique_together     = [('category', 'period_type', 'year', 'month', 'quarter')]
        indexes             = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['year', 'quarter']),
            models.Index(fields=['category', 'year']),
        ]

    def __str__(self):
        period = self.get_period_label()
        return f"{self.category} | {period} | план={self.plan}"

    def get_period_label(self):
        if self.period_type == self.Period.MONTHLY and self.month:
            return f"{self.month:02d}.{self.year}"
        if self.period_type == self.Period.QUARTERLY and self.quarter:
            return f"Q{self.quarter} {self.year}"
        return str(self.year)

    @property
    def variance(self):
        return self.fact - self.plan

    @property
    def variance_pct(self):
        if self.plan == 0:
            return None
        return round((self.fact - self.plan) / self.plan * 100, 2)

    @property
    def execution_pct(self):
        if self.plan == 0:
            return None
        return round(self.fact / self.plan * 100, 2)

class FinancialStatement(models.Model):

    class Period(models.TextChoices):
        MONTHLY   = 'monthly',   'Месяц'
        QUARTERLY = 'quarterly', 'Квартал'
        YEARLY    = 'yearly',    'Год'

    period_type = models.CharField('Тип периода', max_length=10, choices=Period.choices, default=Period.MONTHLY, db_index=True)
    year    = models.PositiveIntegerField('Год', db_index=True)
    month   = models.PositiveSmallIntegerField('Месяц (1-12)', null=True, blank=True)
    quarter = models.PositiveSmallIntegerField('Квартал (1-4)', null=True, blank=True)

    revenue_plan     = models.DecimalField('Выручка план', max_digits=16, decimal_places=2, default=0)
    revenue_fact     = models.DecimalField('Выручка факт', max_digits=16, decimal_places=2, default=0)
    revenue_forecast = models.DecimalField('Выручка прогноз', max_digits=16, decimal_places=2, default=0)

    ebitda_plan     = models.DecimalField('EBITDA план', max_digits=16, decimal_places=2, default=0)
    ebitda_fact     = models.DecimalField('EBITDA факт', max_digits=16, decimal_places=2, default=0)
    ebitda_forecast = models.DecimalField('EBITDA прогноз', max_digits=16, decimal_places=2, default=0)

    operating_profit_plan = models.DecimalField('Операционная прибыль план', max_digits=16, decimal_places=2, default=0)
    operating_profit_fact = models.DecimalField('Операционная прибыль факт', max_digits=16, decimal_places=2, default=0)

    net_profit_plan     = models.DecimalField('Чистая прибыль план', max_digits=16, decimal_places=2, default=0)
    net_profit_fact     = models.DecimalField('Чистая прибыль факт', max_digits=16, decimal_places=2, default=0)
    net_profit_forecast = models.DecimalField('Чистая прибыль прогноз', max_digits=16, decimal_places=2, default=0)

    revenue_categories = models.ManyToManyField(
        BudgetCategory, blank=True,
        related_name='revenue_statements',
        verbose_name='Категории выручки',
        limit_choices_to={'category_type': 'income'},
    )
    expense_categories = models.ManyToManyField(
        BudgetCategory, blank=True,
        related_name='expense_statements',
        verbose_name='Категории расходов',
        limit_choices_to={'category_type': 'expense'},
    )

    note       = models.TextField('Примечание', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude=exclude)
        from django.core.exceptions import ValidationError
        qs = FinancialStatement.objects.filter(
            period_type=self.period_type,
            year=self.year,
            month=self.month,
            quarter=self.quarter,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
            f'Отчёт ОПиУ за этот период уже существует.'
        )


    class Meta:
        verbose_name        = 'Отчёт ОПиУ'
        verbose_name_plural = 'Отчёты ОПиУ'
        ordering            = ['-year', '-month', '-quarter']
        unique_together     = [('period_type', 'year', 'month', 'quarter')]
        indexes             = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['period_type', 'year']),
        ]

    def __str__(self):
        return f"ОПиУ | {self.get_period_label()}"

    def get_period_label(self):
        if self.period_type == self.Period.MONTHLY and self.month:
            return f"{self.month:02d}.{self.year}"
        if self.period_type == self.Period.QUARTERLY and self.quarter:
            return f"Q{self.quarter} {self.year}"
        return str(self.year)

    @property
    def ebitda_margin_fact(self):
        if not self.revenue_fact:
            return None
        return round(self.ebitda_fact / self.revenue_fact * 100, 2)

    @property
    def net_margin_fact(self):
        if not self.revenue_fact:
            return None
        return round(self.net_profit_fact / self.revenue_fact * 100, 2)

    @property
    def operating_margin_fact(self):
        if not self.revenue_fact:
            return None
        return round(self.operating_profit_fact / self.revenue_fact * 100, 2)

    @property
    def revenue_variance(self):
        return self.revenue_fact - self.revenue_plan

    @property
    def net_profit_variance(self):
        return self.net_profit_fact - self.net_profit_plan

    @property
    def ebitda_variance(self):
        return self.ebitda_fact - self.ebitda_plan

class CashFlowRecord(models.Model):
    class Direction(models.TextChoices):
        INFLOW  = 'inflow',  'Поступление'
        OUTFLOW = 'outflow', 'Списание'

    class FlowType(models.TextChoices):
        OPERATING  = 'operating',  'Операционная деятельность'
        INVESTING  = 'investing',  'Инвестиционная деятельность'
        FINANCING  = 'financing',  'Финансовая деятельность'

    direction    = models.CharField(
        'Направление', max_length=10,
        choices=Direction.choices,
        db_index=True,
    )
    flow_type    = models.CharField(
        'Тип деятельности', max_length=15,
        choices=FlowType.choices,
        default=FlowType.OPERATING,
        db_index=True,
    )
    amount       = models.DecimalField('Сумма', max_digits=16, decimal_places=2)
    currency     = models.CharField('Валюта', max_length=3, default='KZT')
    transaction_date = models.DateField('Дата операции', db_index=True)
    value_date   = models.DateField('Дата валютирования', null=True, blank=True)

    description  = models.TextField('Назначение платежа', null=True, blank=True)
    document_number = models.CharField('Номер документа', max_length=100, null=True, blank=True)

    bank_account = models.CharField('Банковский счёт', max_length=100, null=True, blank=True)

    counterparty = models.ForeignKey(
        'onec.Counterparty',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cash_flow_records',
        verbose_name='Контрагент',
    )
    budget_category = models.ForeignKey(
        BudgetCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cash_flow_records',
        verbose_name='Статья бюджета',
    )

    onec_id   = models.CharField('ID в 1С', max_length=100, unique=True, null=True, blank=True)
    onec_document_type = models.CharField('Тип документа 1С', max_length=100, null=True, blank=True)
    synced_at = models.DateTimeField('Дата синхронизации', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Запись ДДС'
        verbose_name_plural = 'Реестр ДДС'
        ordering            = ['-transaction_date', '-created_at']
        indexes             = [
            models.Index(fields=['transaction_date']),
            models.Index(fields=['direction']),
            models.Index(fields=['flow_type']),
            models.Index(fields=['counterparty']),
            models.Index(fields=['budget_category']),
            models.Index(fields=['transaction_date', 'direction']),
        ]

    def __str__(self):
        return (
            f"{self.get_direction_display()} | "
            f"{self.transaction_date.strftime('%d.%m.%Y')} | "
            f"{self.amount} {self.currency}"
        )

    @property
    def is_inflow(self):
        return self.direction == self.Direction.INFLOW

    @property
    def is_outflow(self):
        return self.direction == self.Direction.OUTFLOW


class CreditModel(models.Model):
    class Scenario(models.TextChoices):
        BASE       = 'base',       'Базовый'
        STRESS     = 'stress',     'Стрессовый'
        OPTIMISTIC = 'optimistic', 'Оптимистичный'

    class RiskLevel(models.TextChoices):
        LOW    = 'low',    'Низкий'
        MEDIUM = 'medium', 'Средний'
        HIGH   = 'high',   'Высокий'

    name        = models.CharField('Название', max_length=200)
    scenario    = models.CharField(
        'Сценарий', max_length=15,
        choices=Scenario.choices,
        default=Scenario.BASE,
        db_index=True,
    )
    year        = models.PositiveIntegerField('Год прогноза', db_index=True)
    description = models.TextField('Описание', null=True, blank=True)
    loan_amount      = models.DecimalField('Сумма кредита',      max_digits=16, decimal_places=2, default=0)
    loan_rate        = models.DecimalField('Процентная ставка %', max_digits=6,  decimal_places=2, default=0)
    loan_term_months = models.PositiveIntegerField('Срок кредита (мес)', default=12)
    annual_debt_service = models.DecimalField(
        'Годовое обслуживание долга', max_digits=16, decimal_places=2, default=0
    )

    forecast_pnl = models.JSONField(
        'Прогнозный ОПиУ', default=dict, blank=True,
        help_text='{"revenue": 0, "ebitda": 0, "operating_profit": 0, "net_profit": 0}'
    )

    forecast_cashflow = models.JSONField(
        'Прогнозный Cash Flow', default=dict, blank=True,
        help_text='{"operating": 0, "investing": 0, "financing": 0, "free_cashflow": 0}'
    )

    financial_statement = models.ForeignKey(
        FinancialStatement,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='credit_models',
        verbose_name='Отчёт ОПиУ',
    )

    risk_level = models.CharField(
        'Уровень риска', max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.MEDIUM,
        db_index=True,
    )
    risk_notes = models.TextField('Комментарий по рискам', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Кредитная модель'
        verbose_name_plural = 'Кредитные модели'
        ordering            = ['-year', 'scenario']
        unique_together     = [('name', 'scenario', 'year')]
        indexes             = [
            models.Index(fields=['scenario']),
            models.Index(fields=['risk_level']),
            models.Index(fields=['year', 'scenario']),
        ]

    def __str__(self):
        return f"{self.name} | {self.get_scenario_display()} | {self.year}"


    @property
    def ebitda(self):
        return self.forecast_pnl.get('ebitda', 0)

    @property
    def free_cashflow(self):
        return self.forecast_cashflow.get('free_cashflow', 0)

    @property
    def dscr(self):
        if not self.annual_debt_service or not self.ebitda:
            return None
        try:
            return round(float(self.ebitda) / float(self.annual_debt_service), 2)
        except (TypeError, ZeroDivisionError):
            return None

    @property
    def dscr_status(self):
        d = self.dscr
        if d is None:
            return 'unknown'
        if d >= 1.5:
            return 'excellent'
        if d >= 1.2:
            return 'good'
        if d >= 1.0:
            return 'acceptable'
        return 'critical'

    @property
    def revenue_forecast(self):
        return self.forecast_pnl.get('revenue', 0)

    @property
    def net_profit_forecast(self):
        return self.forecast_pnl.get('net_profit', 0)

    @property
    def operating_cashflow(self):
        return self.forecast_cashflow.get('operating', 0)

    def save(self, *args, **kwargs):
        if self.financial_statement:
            fs = self.financial_statement
            
            self.forecast_pnl = {
                'revenue': float(fs.revenue_forecast or 0),
                'ebitda': float(fs.ebitda_forecast or 0),
                'operating_profit': float(fs.operating_profit_forecast or 0) if hasattr(fs, 'operating_profit_forecast') else 0,
                'net_profit': float(fs.net_profit_forecast or 0)
            }
            
            ebitda_val = float(fs.ebitda_forecast or 0)
            monthly_debt_service = float(self.annual_debt_service or 0) / 12.0
            op_cf = ebitda_val
            fin_cf = -monthly_debt_service * float(self.loan_term_months) if self.loan_term_months else 0
            free_cf = op_cf - float(self.annual_debt_service or 0)

            self.forecast_cashflow = {
                'operating': op_cf,
                'investing': 0.0,
                'financing': fin_cf,
                'free_cashflow': free_cf
            }
            
            dscr_val = self.dscr
            if dscr_val is None:
                self.risk_level = CreditModel.RiskLevel.MEDIUM
            elif dscr_val >= 1.5:
                self.risk_level = CreditModel.RiskLevel.LOW
            elif dscr_val >= 1.0:
                self.risk_level = CreditModel.RiskLevel.MEDIUM
            else:
                self.risk_level = CreditModel.RiskLevel.HIGH

        super().save(*args, **kwargs)


class ExchangeRate(models.Model):
    currency = models.CharField(
        "Код валюты",
        max_length=10,
        help_text="ISO 4217, например: USD, EUR, RUB",
    )
    date = models.DateField("Дата курса")
    rate = models.DecimalField(
        "Курс к KZT",
        max_digits=18,
        decimal_places=4,
    )

    class Meta:
        unique_together = ("currency", "date")
        ordering = ["-date", "currency"]
        verbose_name = "Курс валюты"
        verbose_name_plural = "Курсы валют"
        indexes = [
            models.Index(fields=["currency", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"{self.currency}/KZT = {self.rate} ({self.date})"
    @classmethod
    def get_rate(cls, currency: str, date) -> "ExchangeRate":
        currency = currency.upper().strip()
        if currency == "KZT":
            return cls(currency="KZT", date=date, rate=Decimal("1.0"))
        return cls.objects.get(currency=currency, date=date)

    @classmethod
    def get_latest_rate(cls, currency: str) -> "ExchangeRate":
        currency = currency.upper().strip()
        if currency == "KZT":
            import datetime
            return cls(currency="KZT", date=datetime.date.today(), rate=Decimal("1.0"))
        return cls.objects.filter(currency=currency).latest("date")

    @classmethod
    def convert(
        cls,
        amount,
        from_currency: str,
        to: str = "KZT",
        date=None,
    ) -> Decimal:
        amount = Decimal(str(amount))
        from_currency = from_currency.upper().strip()
        to = to.upper().strip()

        if from_currency == to:
            return amount

        def _get(currency):
            if date:
                return cls.get_rate(currency, date).rate
            return cls.get_latest_rate(currency).rate

        if to == "KZT":
            return (amount * _get(from_currency)).quantize(Decimal("0.01"))

        if from_currency == "KZT":
            to_rate = _get(to)
            if to_rate == 0:
                raise ValueError(f"Нулевой курс для {to}")
            return (amount / to_rate).quantize(Decimal("0.000001"))

        amount_in_kzt = amount * _get(from_currency)
        to_rate = _get(to)
        if to_rate == 0:
            raise ValueError(f"Нулевой курс для {to}")
        return (amount_in_kzt / to_rate).quantize(Decimal("0.000001"))