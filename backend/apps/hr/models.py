from django.db import models
from account.models import UserAccount
from account.models import Employee

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



class Position(models.Model):
    title = models.CharField("Наименование должности", max_length=255)
    department = models.ForeignKey(
        'account.Department', 
        on_delete=models.CASCADE, 
        related_name='positions',
        verbose_name="Департамент"
    )
    description = models.TextField("Описание", blank=True, null=True)

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"
        unique_together = ['title', 'department']

    def __str__(self):
        return f"{self.title} ({self.department.name})"    


class Vacation(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='vacations',
        verbose_name="Сотрудник"
    )

    type = models.CharField("Тип", max_length=50)
    start_date = models.DateField("Дата начала")
    end_date = models.DateField("Дата окончания")
    status = models.CharField("Статус", max_length=50)

    enbek_id = models.CharField("ID Enbek", max_length=100, unique=True)

    def __str__(self):
        return f"{self.employee} | {self.start_date}"

    class Meta:
        verbose_name = "Отпуск (Enbek)"
        verbose_name_plural = "Отпуска (Enbek)"


class SickLeave(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sick_leaves',
        verbose_name="Сотрудник"
    )

    start_date = models.DateField("Дата начала")
    end_date = models.DateField("Дата окончания")

    document_number = models.CharField("Номер документа", max_length=100, null=True, blank=True)

    enbek_id = models.CharField("ID Enbek", max_length=100, unique=True)

    def __str__(self):
        return f"{self.employee} | {self.start_date}"

    class Meta:
        verbose_name = "Больничный (Enbek)"
        verbose_name_plural = "Больничные (Enbek)"


class EmploymentContract(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='employment_contracts',
        verbose_name="Сотрудник"
    )

    number = models.CharField("Номер", max_length=100, null=True, blank=True)
    date = models.DateField("Дата", null=True, blank=True)

    type = models.CharField("Тип", max_length=50)
    status = models.CharField("Статус", max_length=50)

    enbek_id = models.CharField("ID Enbek", max_length=100, unique=True)

    def __str__(self):
        return f"{self.employee} | {self.number}"

    class Meta:
        verbose_name = "Трудовой договор (Enbek)"
        verbose_name_plural = "Трудовые договоры (Enbek)"
