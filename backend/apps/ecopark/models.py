import uuid
from math import radians, sin, cos, sqrt, atan2

from django.db import models
from django.utils import timezone

# Точка обхода (Венткамера, Электрощитовая и т.п.) — как правило, помещение
# внутри здания, где GPS у телефона регулярно "плывёт" на десятки метров.
# Порог намеренно щедрый: цель — поймать явную подмену (отметился из дома),
# а не наказывать за обычную погрешность GPS в помещении.
GEO_MISMATCH_THRESHOLD_M = 200


def _haversine_m(lat1, lon1, lat2, lon2):
    """Расстояние между двумя точками (широта/долгота) в метрах."""
    r = 6371000
    phi1, phi2 = radians(float(lat1)), radians(float(lat2))
    dphi = radians(float(lat2) - float(lat1))
    dlambda = radians(float(lon2) - float(lon1))
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


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


class ChecklistTemplate(models.Model):
    name = models.CharField('Название', max_length=255)
    is_active = models.BooleanField('Активен', default=True)
    created_by = models.ForeignKey(
        'account.UserAccount', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_checklist_templates',
        verbose_name='Создал',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Чек-лист'
        verbose_name_plural = 'Чек-листы'
        ordering = ['name']

    def __str__(self):
        return self.name


class ChecklistItem(models.Model):
    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.CASCADE, related_name='items',
        verbose_name='Чек-лист',
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    text = models.CharField('Пункт', max_length=500)
    requires_photo_on_fail = models.BooleanField(
        'Требовать фото при несоответствии', default=True,
    )

    class Meta:
        verbose_name = 'Пункт чек-листа'
        verbose_name_plural = 'Пункты чек-листа'
        ordering = ['template', 'order', 'id']

    def __str__(self):
        return self.text


class RoundPoint(models.Model):
    uuid = models.UUIDField('UUID', default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField('Название', max_length=255)
    location = models.CharField('Местоположение', max_length=255, blank=True)
    eco_object = models.ForeignKey(
        EcoObject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='round_points', verbose_name='Объект',
    )
    checklist = models.ForeignKey(
        ChecklistTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='points', verbose_name='Чек-лист',
    )
    check_interval_hours = models.PositiveIntegerField(
        'Интервал проверки, ч', default=24,
    )
    latitude = models.DecimalField(
        'Широта', max_digits=10, decimal_places=7, null=True, blank=True,
    )
    longitude = models.DecimalField(
        'Долгота', max_digits=10, decimal_places=7, null=True, blank=True,
    )
    is_active = models.BooleanField('Активна', default=True)
    created_by = models.ForeignKey(
        'account.UserAccount', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_round_points',
        verbose_name='Создал',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Точка обхода'
        verbose_name_plural = 'Точки обхода'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def last_visit(self):
        return self.visits.order_by('-created_at').first()

    @property
    def is_overdue(self):
        deadline_base = self.last_visit.created_at if self.last_visit else self.created_at
        return timezone.now() > deadline_base + timezone.timedelta(hours=self.check_interval_hours)


class Equipment(models.Model):
    # CASCADE — оборудование это просто справочная опись точки, отдельной
    # истории по нему не ведём (в отличие от визитов/ответов/неисправностей).
    point = models.ForeignKey(
        RoundPoint, on_delete=models.CASCADE, related_name='equipment',
        verbose_name='Точка',
    )
    name = models.CharField('Название', max_length=255)
    description = models.CharField('Описание', max_length=1000, blank=True)
    is_active = models.BooleanField('Активно', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Оборудование'
        verbose_name_plural = 'Оборудование'
        ordering = ['point', 'name']

    def __str__(self):
        return f"{self.name} ({self.point.name})"


class RoundVisit(models.Model):
    # PROTECT, не CASCADE: удаление точки не должно стирать историю обходов
    # по ней (требование "сохранение исторических данных") — точку с
    # визитами можно только деактивировать, см. round_point_delete().
    point = models.ForeignKey(
        RoundPoint, on_delete=models.PROTECT, related_name='visits',
        verbose_name='Точка',
    )
    employee = models.ForeignKey(
        'account.Employee', on_delete=models.CASCADE, related_name='round_visits',
        verbose_name='Сотрудник',
    )
    comment = models.CharField('Комментарий', max_length=1000, blank=True)
    latitude = models.DecimalField(
        'Широта', max_digits=10, decimal_places=7, null=True, blank=True,
    )
    longitude = models.DecimalField(
        'Долгота', max_digits=10, decimal_places=7, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    GEO_OK = 'ok'
    GEO_MISMATCH = 'mismatch'
    GEO_MISSING = 'missing'
    GEO_UNKNOWN = 'unknown'

    class Meta:
        verbose_name = 'Обход точки'
        verbose_name_plural = 'Обходы точек'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.point} | {self.employee} | {self.created_at:%d.%m.%Y %H:%M}"

    @property
    def has_failed_items(self):
        return self.answers.filter(passed=False).exists()

    @property
    def geo_distance_m(self):
        if self.point.latitude is None or self.point.longitude is None:
            return None
        if self.latitude is None or self.longitude is None:
            return None
        return round(_haversine_m(self.point.latitude, self.point.longitude, self.latitude, self.longitude))

    @property
    def geo_status(self):
        """
        Сверка геолокации с координатами точки — попытка поймать отметку
        "не отходя от дома" по статичному (печатному) QR, у которого нет
        своей защиты от копирования в отличие от короткоживущих токенов
        check-in'а. Не блокирует отправку — только помечает для проверки
        руководителем, т.к. GPS в помещении регулярно врёт на десятки метров.
        """
        if self.point.latitude is None or self.point.longitude is None:
            return self.GEO_UNKNOWN
        if self.latitude is None or self.longitude is None:
            return self.GEO_MISSING
        distance = self.geo_distance_m
        return self.GEO_MISMATCH if distance > GEO_MISMATCH_THRESHOLD_M else self.GEO_OK


class RoundVisitAnswer(models.Model):
    visit = models.ForeignKey(
        RoundVisit, on_delete=models.CASCADE, related_name='answers',
        verbose_name='Обход',
    )
    # PROTECT: тот же принцип, что у RoundVisit.point — исторический ответ
    # не должен пропасть, если админ потом уберёт пункт из чек-листа.
    item = models.ForeignKey(
        ChecklistItem, on_delete=models.PROTECT, related_name='answers',
        verbose_name='Пункт',
    )
    passed = models.BooleanField('Соответствует')
    comment = models.CharField('Комментарий', max_length=500, blank=True)
    photo = models.ImageField(
        'Фото', upload_to='ecopark/rounds/%Y/%m/%d/', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Ответ по пункту'
        verbose_name_plural = 'Ответы по пунктам'
        ordering = ['item__order', 'id']

    def __str__(self):
        return f"{self.item} — {'ок' if self.passed else 'несоответствие'}"


class Defect(models.Model):
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Открыта'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_RESOLVED, 'Устранена'),
    ]

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

    visit = models.ForeignKey(
        RoundVisit, on_delete=models.CASCADE, related_name='defects',
        verbose_name='Обход',
    )
    answer = models.ForeignKey(
        RoundVisitAnswer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='defects', verbose_name='Ответ',
    )
    point = models.ForeignKey(
        RoundPoint, on_delete=models.PROTECT, related_name='defects',
        verbose_name='Точка',
    )
    description = models.CharField('Описание', max_length=1000)
    photo = models.ImageField(
        'Фото', upload_to='ecopark/defects/%Y/%m/%d/', null=True, blank=True,
    )
    status = models.CharField(
        'Статус', max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN,
    )
    priority = models.CharField(
        'Приоритет', max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM,
    )
    assigned_to = models.ForeignKey(
        'account.UserAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_defects', verbose_name='Назначена',
    )
    escalated_at = models.DateTimeField('Эскалирована', null=True, blank=True)
    reported_by = models.ForeignKey(
        'account.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reported_defects', verbose_name='Обнаружил',
    )
    resolved_by = models.ForeignKey(
        'account.UserAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_defects', verbose_name='Устранил',
    )
    resolved_at = models.DateTimeField('Устранена', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Неисправность'
        verbose_name_plural = 'Неисправности'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.point} | {self.description[:40]}"
