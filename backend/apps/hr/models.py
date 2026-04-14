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
    