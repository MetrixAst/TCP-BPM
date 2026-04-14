from django.db import models
from .enums import SupplierStatusEnum, SupplierCheckedStatusEnum, SupplierFormEnum, SupplierTypeEnum
from account.models import UserAccount

class Country(models.Model):

    title = models.CharField("Название", max_length=30)
    
    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Страна"
        verbose_name_plural = "Страны"
        ordering = ['title']


class City(models.Model):

    title = models.CharField("Название", max_length=30)
    
    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Город"
        verbose_name_plural = "Города"
        ordering = ['title']


class SupplierCategory(models.Model):

    title = models.CharField("Название", max_length=30)
    
    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Категория контрагента"
        verbose_name_plural = "Категории контрагента"
        ordering = ['title']


class Supplier(models.Model):

    author = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, related_name="suppliers", verbose_name="Создано", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    country = models.ForeignKey(Country, on_delete=models.SET_NULL, verbose_name="Страна", null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, verbose_name="Город", null=True, blank=True)
    category = models.ManyToManyField(SupplierCategory, verbose_name="Категории", blank=True)

    status = models.SlugField("Статус", choices=SupplierStatusEnum.list())
    check_status = models.SlugField("Результат проверки", choices=SupplierCheckedStatusEnum.list(), null=True, blank=True)
    form = models.SlugField("Форма собственности", choices=SupplierFormEnum.list(), null=True, blank=True)
    supplier_type = models.SlugField("Юр./физ. лицо", choices=SupplierTypeEnum.list(), null=True, blank=True)

    reg_date = models.DateField(verbose_name="Дата регистрации", null=True, blank=True)

    identifier = models.CharField("БИН/ИИН", max_length=40, null=True, blank=True)
    kbe = models.CharField("КБЕ", max_length=40, null=True, blank=True)
    address1 = models.CharField("Юр. адрес", max_length=60, null=True, blank=True)
    address2 = models.CharField("Фактический адрес", max_length=60)

    head_name = models.CharField("ФИО учредителя", max_length=40, null=True, blank=True)
    head_status = models.CharField("Статус учредителя", max_length=40, null=True, blank=True)
    phone = models.CharField("Телефон", max_length=40, null=True, blank=True)
    email = models.EmailField("E-mail", max_length=40, null=True, blank=True)

    certificate_serie = models.CharField("Серия свидетельства", max_length=40, null=True, blank=True)
    certificate_number = models.CharField("Номер свидетельства", max_length=40, null=True, blank=True)
    certificate_date = models.CharField("Дата свидетельства", max_length=40, null=True, blank=True)

    contacts = models.CharField("Контакты", max_length=100, null=True, blank=True)
    adata_link = models.URLField("Ссылка на карточку ADATA.KZ", max_length=100, null=True, blank=True)
    oked = models.CharField("Основной ОКЭД", max_length=100, null=True, blank=True)
    name = models.CharField("Полное наименование", max_length=100)

    problems = models.CharField("Есть проблемы", max_length=100, null=True, blank=True)
    size = models.CharField("Размер предприятия", max_length=100, null=True, blank=True)

    lawyer = models.CharField("Юрист", max_length=100, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"
        ordering = ['name']


    @property
    def status_color(self):
        return SupplierStatusEnum.get_color(self.status)
    
    @property
    def categories_list(self):
        categories = list(self.category.all().values_list('title', flat=True))
        return ", ".join(categories)