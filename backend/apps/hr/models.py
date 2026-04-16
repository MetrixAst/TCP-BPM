from django.db import models
from account.models import UserAccount

from .enums import CalendarItemType

class CalendarItem(models.Model):

    TYPES = CalendarItemType.list()

    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Пользователь", null=True, blank=True)
    title = models.CharField("Заголовок", max_length=100, null=True, blank=True)
    start_date = models.DateField(verbose_name="Дата")
    end_date = models.DateField(verbose_name="Завершение")
    category = models.SlugField("Тип", choices=TYPES)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Календарь (hr)"
        verbose_name_plural = "Календарь (hr)"
        ordering = ['-id']

    @property
    def start(self):
        return self.start_date

    @property
    def end(self):
        return self.end_date


class Company(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    bin_number = models.CharField(
        max_length=12, 
        unique=True, 
        verbose_name="БИН"
    )

    address = models.TextField(blank=True, null=True, verbose_name="Адрес")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Компания"
        verbose_name_plural = "Компании"
    