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