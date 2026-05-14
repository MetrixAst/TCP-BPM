from django.db import models
from account.models import UserAccount

from .enums import FinanceItemType

from tenants.models import Tenant

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