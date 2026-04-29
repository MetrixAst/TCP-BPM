from django.db import models
from account.models import UserAccount

from .enums import CalendarItemType, DayTypeEnum


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

    def get_employees_count(self):
        from account.models import Employee
        return Employee.objects.filter(department__company=self).count()

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

class WorkCalendar(models.Model):
    company = models.ForeignKey(
        'hr.Company', 
        on_delete=models.CASCADE, 
        related_name='work_calendars',
        verbose_name="Компания",
        null=True,   
        blank=True   
    )
    year = models.IntegerField("Год")
    date = models.DateField("Дата")
    day_type = models.CharField(
        "Тип дня", 
        max_length=20, 
        choices=DayTypeEnum.choices, 
        default=DayTypeEnum.WORKING
    )

    class Meta:
        verbose_name = "Производственный календарь"
        verbose_name_plural = "Производственный календарь"
        unique_together = ('company', 'date')
        ordering = ['date']

    def __str__(self):
        company_name = self.company.name if self.company else "Общий (РК)"
        return f"{self.date} ({company_name})"

    @staticmethod
    def is_working_day(date_to_check, company):
        day_record = WorkCalendar.objects.filter(company=company, date=date_to_check).first()
        if not day_record:
            day_record = WorkCalendar.objects.filter(company__isnull=True, date=date_to_check).first()
        if day_record:
            return day_record.day_type == DayTypeEnum.WORKING
        
        return date_to_check.weekday() < 5