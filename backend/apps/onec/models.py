from django.db import models




class Remnant(models.Model):

    QuantityRemainder = models.FloatField("Остаток", null=True, blank=True)

    Nomenclature = models.CharField("Номенклатура", max_length=100, null=True, blank=True)
    NomenclatureCode = models.CharField("Код номенклатуры", max_length=100, null=True, blank=True)

    Storehouse = models.CharField("Склад", max_length=100, null=True, blank=True)
    StorehouseCode = models.CharField("Код склада", max_length=100, null=True, blank=True)

    def __str__(self):
        return self.Nomenclature or "--"

    class Meta:
        verbose_name = "Остаток"
        verbose_name_plural = "Остатки"
        ordering = ['NomenclatureCode']


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создан'),
        ('sent', 'Отправлен'),
        ('viewed', 'Просмотрен'),
        ('paid', 'Оплачен'),
    ]

    counterparty = models.ForeignKey(
        'Counterparty', 
        on_delete=models.PROTECT, 
        related_name='invoices',
        verbose_name="Контрагент",
        null=True, 
        blank=True
    )
    number = models.CharField("Номер счета", max_length=50, null=True, blank=True)
    status = models.CharField(
        "Статус", 
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='created'
    )
    comment = models.TextField("Комментарий", null=True, blank=True)

    Sum = models.FloatField("Сумма", null=True, blank=True)
    Date = models.DateTimeField("Дата", null=True, blank=True)
    CounterpartyAccount = models.CharField("Счет контрагента", max_length=100, null=True, blank=True)
    OrganizationAccount = models.CharField("Счет компании", max_length=100, null=True, blank=True)
    Payment = models.CharField("Тип платежа", max_length=30, null=True, blank=True)

    def __str__(self):
        return f"Счет №{self.number} от {self.Date}" if self.number else f"Счет от {self.Date}"

    class Meta:
        verbose_name = "Счет (Расходы/доходы)"
        verbose_name_plural = "Счета (Расходы/доходы)"
        ordering = ['-Date']


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(
        Invoice, 
        on_delete=models.CASCADE, 
        related_name='items', 
        verbose_name="Счет"
    )
    name = models.CharField("Наименование товара/услуги", max_length=255)
    quantity = models.FloatField("Количество", default=1.0)
    price = models.FloatField("Цена", default=0.0)
    total = models.FloatField("Итого", default=0.0)
    
    vat_rate = models.FloatField("Ставка НДС (%)", default=12.0) 
    vat_amount = models.FloatField("Сумма НДС", default=0.0)


    def save(self, *args, **kwargs):
        self.total = round(self.quantity * self.price, 2)
        self.vat_amount = round(self.total * (self.vat_rate / 100), 2)
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.total})"

    class Meta:
        verbose_name = "Позиция счета"
        verbose_name_plural = "Позиции счета"

class Counterparty(models.Model):
    id_1c = models.CharField("ID 1C", max_length=50, unique=True)
    full_name = models.CharField("Полное наименование", max_length=500)
    short_name = models.CharField("Краткое наименование", max_length=255)
    bin_number = models.CharField("БИН", max_length=12, unique=True, null=True, blank=True)
    iin = models.CharField("ИИН", max_length=12, null=True, blank=True)
    address = models.TextField("Адрес", null=True, blank=True)
    phone = models.CharField("Телефон", max_length=100, null=True, blank=True)
    email = models.EmailField("Email", null=True, blank=True)
    
    is_supplier = models.BooleanField("Поставщик", default=False)
    is_customer = models.BooleanField("Клиент", default=False)
    
    bank_accounts = models.JSONField("Банковские счета", default=list, blank=True)
    contracts = models.JSONField("Договоры", default=list, blank=True)
    
    synced_at = models.DateTimeField("Дата синхронизации", null=True, blank=True)

    def __str__(self):
        return self.short_name or self.full_name

    class Meta:
        verbose_name = "Контрагент"
        verbose_name_plural = "Контрагенты"
        ordering = ['short_name']