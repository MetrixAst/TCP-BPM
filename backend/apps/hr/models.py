from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
from account.models import UserAccount, Employee
from datetime import timedelta
from .enums import CalendarItemType, DayTypeEnum, LeaveStatusEnum, CheckInEnum, DocumentTypeEnum, DocumentStatusEnum



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

    def save(self, *args, **kwargs):
        if isinstance(self.date, str):
            from datetime import datetime
            self.date = datetime.strptime(self.date, '%Y-%m-%d').date()
            
        self.year = self.date.year
        super().save(*args, **kwargs)

    @staticmethod
    def is_working_day(date_to_check, company):
        if isinstance(date_to_check, str):
            from datetime import datetime
            date_to_check = datetime.strptime(date_to_check, '%Y-%m-%d').date()

        day_record = WorkCalendar.objects.filter(company=company, date=date_to_check).first()
        
        if not day_record:
            day_record = WorkCalendar.objects.filter(company__isnull=True, date=date_to_check).first()
            
        if day_record:
            return day_record.day_type == DayTypeEnum.WORKING
            
        return date_to_check.weekday() < 5

class LeaveType(models.Model):
    name = models.CharField("Название", max_length=100)
    is_paid = models.BooleanField("Оплачиваемый", default=True)
    max_days_per_year = models.PositiveIntegerField("Макс. дней в году", default=24)

    class Meta:
        verbose_name = "Тип отпуска"
        verbose_name_plural = "Типы отпусков"

    def __str__(self):
        return self.name


class LeaveRequest(models.Model):
    employee = models.ForeignKey('account.Employee', on_delete=models.CASCADE, related_name='leave_requests', verbose_name="Сотрудник")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, verbose_name="Тип отпуска")
    start_date = models.DateField("Дата начала")
    end_date = models.DateField("Дата окончания")
    working_days_count = models.PositiveIntegerField("Количество рабочих дней", editable=False, default=0)
    
    comment = models.TextField("Комментарий", blank=True, null=True)
    status = models.CharField("Статус", max_length=20, choices=LeaveStatusEnum.choices, default=LeaveStatusEnum.DRAFT)
    
    approver = models.ForeignKey('account.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves', verbose_name="Кто одобряет")
    
    external_enbek_id = models.CharField("ID в Enbek", max_length=100, null=True, blank=True)
    sync_status = models.CharField("Статус синхронизации", max_length=20, default='local')

    class Meta:
        verbose_name = "Заявка на отпуск"
        verbose_name_plural = "Заявки на отпуск"

    def calculate_working_days(self):
        count = 0
        current_date = self.start_date
        company = self.employee.department.company if self.employee.department else None

        while current_date <= self.end_date:
            if WorkCalendar.is_working_day(current_date, company):
                count += 1
            current_date += timedelta(days=1)
        return count

    def save(self, *args, **kwargs):
        self.working_days_count = self.calculate_working_days()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date})"
        
        return date_to_check.weekday() < 5

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

class AttendanceRecord(models.Model):
    employee = models.ForeignKey(
        'account.Employee', 
        on_delete=models.CASCADE, 
        related_name='attendance_records',
        verbose_name="Сотрудник"
    )
    event_type = models.CharField(
        "Тип события", 
        max_length=20, 
        choices=CheckInEnum.choices
    )
    timestamp = models.DateTimeField("Время", default=timezone.now)
    photo = models.ImageField(
        "Фотофиксация", 
        upload_to='attendance/%Y/%m/%d/', 
        null=True, 
        blank=True
    )
    ip_address = models.GenericIPAddressField("IP адрес", null=True, blank=True)
    workstation = models.CharField("Рабочая станция", max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Запись посещаемости"
        verbose_name_plural = "Записи посещаемости"
        ordering = ['-timestamp']

    def clean(self):
        today = self.timestamp.date() if self.timestamp else timezone.now().date()
        exists = AttendanceRecord.objects.filter(
            employee=self.employee,
            event_type=self.event_type,
            timestamp__date=today
        ).exclude(pk=self.pk).exists()

        if exists:
            raise ValidationError(
                f"Событие '{self.get_event_type_display()}' уже зафиксировано на сегодня ({today})."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @staticmethod
    def get_daily_summary(employee, target_date):
        records = AttendanceRecord.objects.filter(
            employee=employee, 
            timestamp__date=target_date
        ).order_by('timestamp')

        events = {r.event_type: r.timestamp for r in records}
        
        result = {
            'total_work_time': timedelta(0),
            'is_complete': False,
            'details': events
        }

        if CheckInEnum.DAY_START in events and CheckInEnum.DAY_END in events:
            total_duration = events[CheckInEnum.DAY_END] - events[CheckInEnum.DAY_START]
            
            lunch_duration = timedelta(0)
            if CheckInEnum.LUNCH_START in events and CheckInEnum.LUNCH_END in events:
                lunch_duration = events[CheckInEnum.LUNCH_END] - events[CheckInEnum.LUNCH_START]
            
            result['total_work_time'] = total_duration - lunch_duration
            result['is_complete'] = True
            
        return result

    def __str__(self):
        return f"{self.employee} - {self.event_type} ({self.timestamp.strftime('%d.%m %H:%M')})"

class EmployeeDocument(models.Model):
    employee = models.ForeignKey(
        'account.Employee',
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name="Сотрудник"
    )
    doc_type = models.CharField(
        "Тип документа",
        max_length=30,
        choices=DocumentTypeEnum.choices,
        default=DocumentTypeEnum.OTHER
    )
    title = models.CharField("Название", max_length=255)
    version = models.PositiveIntegerField("Версия", default=1)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=DocumentStatusEnum.choices,
        default=DocumentStatusEnum.DRAFT
    )
    file = models.FileField(
        "Файл",
        upload_to='employee_documents/%Y/%m/',
        null=True,
        blank=True
    )
    signed_at = models.DateField("Дата подписания", null=True, blank=True)
    expires_at = models.DateField("Дата истечения", null=True, blank=True)
    notes = models.TextField("Примечания", blank=True, null=True)
    external_enbek_id = models.CharField(
        "ID в Enbek",
        max_length=100,
        null=True,
        blank=True
    )
    sync_status = models.CharField(
        "Статус синхронизации",
        max_length=20,
        default='local'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Документ сотрудника"
        verbose_name_plural = "Документы сотрудников"
        ordering = ['-created_at']
        unique_together = ['employee', 'doc_type', 'version']

    def __str__(self):
        return f"{self.employee} | {self.get_doc_type_display()} v{self.version}"


class WorkCategory(models.Model):
    code = models.CharField("Код", max_length=50, unique=True)
    name = models.CharField("Название", max_length=255) 
    name_en = models.CharField("Название (EN)", max_length=255, blank=True)
    category_group = models.CharField("Группа", max_length=100)
    
    risk_level = models.CharField("Уровень риска", max_length=20, choices=[
        ('low', 'Низкий'), ('medium', 'Средний'), ('high', 'Высокий'), ('critical', 'Критический')
    ])
    
    requires_training = models.BooleanField("Требуется обучение", default=True)
    requires_medical_exam = models.BooleanField("Требуется медосмотр", default=False)
    requires_ptw = models.BooleanField("Требуется наряд-допуск (PTW)", default=False)
    requires_ppe = models.BooleanField("Требуется СИЗ", default=False)
    requires_gas_test = models.BooleanField("Требуется газоанализ", default=False)
    requires_supervisor = models.BooleanField("Требуется супервайзер", default=False)
    requires_license = models.BooleanField("Требуется гос. лицензия/удостоверение", default=False)
    
    certificate_validity_months = models.PositiveIntegerField("Срок сертификата (мес)", default=12)
    
    required_ppe = models.JSONField("Список СИЗ", default=list, blank=True)
    related_regulations = models.JSONField("Нормативные акты", default=list, blank=True)

    class Meta:
        verbose_name = "Категория работ"
        verbose_name_plural = "Справочник категорий"
        ordering = ['name'] 

    def __str__(self):
        return self.name 

class EmployeeWorkPermit(models.Model):
    employee = models.ForeignKey('account.Employee', on_delete=models.CASCADE, related_name='work_permits')
    category = models.ForeignKey(WorkCategory, on_delete=models.PROTECT, related_name='permits')
    issue_date = models.DateField("Дата выдачи")
    expiry_date = models.DateField("Дата истечения")
    document_number = models.CharField("Номер удостоверения", max_length=100, blank=True)
    scan = models.FileField("Скан документа", upload_to="hr/permits/", null=True, blank=True)

    class Meta:
        verbose_name = "Допуск сотрудника"
        verbose_name_plural = "Допуски сотрудников"
        unique_together = ('employee', 'category')

    def __str__(self):
        return f"{self.employee} - {self.category.name}" 

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return 0
        delta = self.expiry_date - date.today()
        return delta.days

    @property
    def status_label(self):
        labels = {
            'active': 'АКТИВЕН',
            'expiring': 'ИСТЕКАЕТ',
            'expired': 'ПРОСРОЧЕН'
        }
        return labels.get(self.status, self.status)

    @property
    def status(self):
        days = self.days_until_expiry
        if days < 0: return 'expired'
        if days <= 30: return 'expiring'
        return 'active'