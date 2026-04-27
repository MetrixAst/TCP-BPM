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

    Sum = models.FloatField("Сумма", null=True, blank=True)
    Date = models.DateTimeField("Дата", null=True, blank=True)

    CounterpartyAccount = models.CharField("Счет контрагента", max_length=100, null=True, blank=True)
    OrganizationAccount = models.CharField("Счет компании", max_length=100, null=True, blank=True)

    Payment = models.CharField("Тип платежа", max_length=30, null=True, blank=True)

    def __str__(self):
        return str(self.Date)

    class Meta:
        verbose_name = "Расходы/доходы"
        verbose_name_plural = "Расходы/доходы"
        ordering = ['id']

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