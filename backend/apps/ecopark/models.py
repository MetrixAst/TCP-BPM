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