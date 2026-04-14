from django.db import models
from account.models import UserAccount

from .enums import FinanceItemType

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