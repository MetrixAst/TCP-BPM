from django.db import models


class EcoObject(models.Model):
    name = models.CharField(max_length=255, verbose_name='Объект')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Объект'
        verbose_name_plural = 'Объекты'
        ordering = ['name']

    def __str__(self):
        return self.name


class EcoExecutor(models.Model):
    name = models.CharField(max_length=255, verbose_name='Исполнитель')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Исполнитель'
        verbose_name_plural = 'Исполнители'
        ordering = ['name']

    def __str__(self):
        return self.name


class EcoWork(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('progress', 'В процессе'),
        ('done', 'Выполнен'),
        ('overdue', 'Просрочен'),
    ]

    title = models.CharField(max_length=255, verbose_name='Наименование работ')
    eco_object = models.ForeignKey(EcoObject, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Объект')
    executor = models.ForeignKey(EcoExecutor, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Исполнитель')
    responsible = models.CharField(max_length=255, blank=True, verbose_name='Ответственный')
    document = models.FileField(upload_to='ecopark/', blank=True, null=True, verbose_name='Документ')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Сумма')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    date = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = 'Работа'
        verbose_name_plural = 'Работы'
        ordering = ['-date']

    def __str__(self):
        return self.title


import secrets
from django.utils import timezone
from datetime import timedelta

class InspectionPoint(models.Model):
    TYPE_ELECTRICAL = 'electrical'
    TYPE_VENTILATION = 'ventilation'
    TYPE_PLUMBING = 'plumbing'
    TYPE_OTHER = 'other'
    TYPE_CHOICES = [
        (TYPE_ELECTRICAL, 'Электрощитовая'),
        (TYPE_VENTILATION, 'Венткамера'),
        (TYPE_PLUMBING, 'Сантехнический узел'),
        (TYPE_OTHER, 'Другое'),
    ]

    name = models.CharField('Название', max_length=128)
    point_type = models.CharField('Тип', max_length=32, choices=TYPE_CHOICES, default=TYPE_OTHER)
    location = models.CharField('Расположение', max_length=255, blank=True)
    eco_object = models.ForeignKey(
        EcoObject,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inspection_points',
        verbose_name='Объект',
    )
    qr_code = models.CharField('QR-код', max_length=64, unique=True, blank=True)
    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Точка обхода'
        verbose_name_plural = 'Точки обхода'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_point_type_display()})"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = secrets.token_urlsafe(16)
        super().save(*args, **kwargs)


class Equipment(models.Model):
    point = models.ForeignKey(
        InspectionPoint,
        on_delete=models.CASCADE,
        related_name='equipment',
        verbose_name='Точка',
    )
    name = models.CharField('Название', max_length=128)
    description = models.TextField('Описание', blank=True)
    is_active = models.BooleanField('Активно', default=True)

    class Meta:
        verbose_name = 'Оборудование'
        verbose_name_plural = 'Оборудование'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.point.name})"


class ChecklistItem(models.Model):
    point = models.ForeignKey(
        InspectionPoint,
        on_delete=models.CASCADE,
        related_name='checklist_items',
        verbose_name='Точка',
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    text = models.CharField('Текст пункта', max_length=255)
    is_required = models.BooleanField('Обязательный', default=True)
    is_active = models.BooleanField('Активен', default=True)

    class Meta:
        verbose_name = 'Пункт чек-листа'
        verbose_name_plural = 'Пункты чек-листа'
        ordering = ['point', 'order']

    def __str__(self):
        return f"{self.point.name}: {self.text}"


class InspectionSchedule(models.Model):
    point = models.ForeignKey(
        InspectionPoint,
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name='Точка',
    )
    interval_hours = models.PositiveIntegerField('Интервал (часов)', default=4)
    assigned_to = models.ForeignKey(
        'account.UserAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inspection_schedules',
        verbose_name='Ответственный',
    )
    is_active = models.BooleanField('Активно', default=True)

    class Meta:
        verbose_name = 'Расписание обхода'
        verbose_name_plural = 'Расписания обходов'

    def __str__(self):
        return f"{self.point.name} каждые {self.interval_hours}ч"


class InspectionRound(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_MISSED = 'missed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Ожидает'),
        (STATUS_IN_PROGRESS, 'В процессе'),
        (STATUS_COMPLETED, 'Завершён'),
        (STATUS_MISSED, 'Пропущен'),
    ]

    point = models.ForeignKey(
        InspectionPoint,
        on_delete=models.CASCADE,
        related_name='rounds',
        verbose_name='Точка',
    )
    employee = models.ForeignKey(
        'account.UserAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inspection_rounds',
        verbose_name='Сотрудник',
    )
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    server_time = models.DateTimeField('Серверное время', auto_now_add=True)
    notes = models.TextField('Примечания', blank=True)
    ip_address = models.GenericIPAddressField('IP адрес', null=True, blank=True)

    class Meta:
        verbose_name = 'Обход'
        verbose_name_plural = 'Обходы'
        ordering = ['-server_time']

    def __str__(self):
        return f"{self.point.name} — {self.employee} — {self.server_time:%d.%m.%Y %H:%M}"

    @property
    def is_overdue(self):
        schedule = self.point.schedules.filter(is_active=True).first()
        if not schedule or not self.started_at:
            return False
        return self.completed_at is None and \
               timezone.now() > self.started_at + timedelta(hours=schedule.interval_hours)


class InspectionResult(models.Model):
    STATUS_OK = 'ok'
    STATUS_DEFECT = 'defect'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_OK, 'Исправно'),
        (STATUS_DEFECT, 'Неисправно'),
        (STATUS_SKIPPED, 'Пропущено'),
    ]

    round = models.ForeignKey(
        InspectionRound,
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name='Обход',
    )
    checklist_item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name='Пункт чек-листа',
    )
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_OK)
    notes = models.TextField('Примечание', blank=True)
    photo = models.ImageField('Фото', upload_to='inspection/%Y/%m/%d/', null=True, blank=True)

    class Meta:
        verbose_name = 'Результат обхода'
        verbose_name_plural = 'Результаты обхода'
        unique_together = [('round', 'checklist_item')]

    def __str__(self):
        return f"{self.round} — {self.checklist_item.text}: {self.get_status_display()}"


class Defect(models.Model):
    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_CRITICAL = 'critical'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Низкий'),
        (PRIORITY_MEDIUM, 'Средний'),
        (PRIORITY_HIGH, 'Высокий'),
        (PRIORITY_CRITICAL, 'Критический'),
    ]

    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Открыта'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_RESOLVED, 'Устранена'),
    ]

    result = models.OneToOneField(
        InspectionResult,
        on_delete=models.CASCADE,
        related_name='defect',
        verbose_name='Результат',
    )
    description = models.TextField('Описание неисправности')
    priority = models.CharField('Приоритет', max_length=16, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    assigned_to = models.ForeignKey(
        'account.UserAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_defects',
        verbose_name='Назначен',
    )
    escalated_at = models.DateTimeField('Эскалирован', null=True, blank=True)
    resolved_at = models.DateTimeField('Устранён', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Неисправность'
        verbose_name_plural = 'Неисправности'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.result.round.point.name} — {self.get_priority_display()}"