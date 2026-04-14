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