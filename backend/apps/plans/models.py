from datetime import date

from django.db import models
from django.utils import timezone

from account.models import Department, UserAccount


def month_start(value=None):
    value = value or timezone.localdate()
    return date(value.year, value.month, 1)


class DepartmentPlan(models.Model):
    """План работы отдела на месяц: руководитель вносит, директор/собственник контролирует."""

    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name='plans', verbose_name='Отдел',
    )
    month = models.DateField('Месяц', help_text='Первое число месяца')
    author = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_plans', verbose_name='Автор',
    )
    note = models.TextField('Комментарий к плану', blank=True, default='')
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Изменён', auto_now=True)

    class Meta:
        verbose_name = 'План отдела'
        verbose_name_plural = 'Планы отделов'
        ordering = ['-month', 'department__name']
        constraints = [
            models.UniqueConstraint(fields=['department', 'month'], name='unique_plan_department_month'),
        ]

    def __str__(self):
        return f'{self.department} — {self.month:%m.%Y}'

    def save(self, *args, **kwargs):
        self.month = month_start(self.month)
        super().save(*args, **kwargs)

    def stats(self, items=None):
        items = list(self.items.all()) if items is None else items
        active = [i for i in items if i.status != PlanItem.STATUS_CANCELLED]
        done = sum(1 for i in active if i.status == PlanItem.STATUS_DONE)
        return {
            'total': len(active),
            'done': done,
            'in_progress': sum(1 for i in active if i.status == PlanItem.STATUS_IN_PROGRESS),
            'planned': sum(1 for i in active if i.status == PlanItem.STATUS_PLANNED),
            'overdue': sum(1 for i in active if i.is_overdue),
            'cancelled': len(items) - len(active),
            'progress': round(done / len(active) * 100) if active else 0,
        }


class PlanItem(models.Model):
    STATUS_PLANNED = 'planned'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PLANNED, 'Запланировано'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_DONE, 'Выполнено'),
        (STATUS_CANCELLED, 'Отменено'),
    ]
    OPEN_STATUSES = (STATUS_PLANNED, STATUS_IN_PROGRESS)

    plan = models.ForeignKey(DepartmentPlan, on_delete=models.CASCADE, related_name='items', verbose_name='План')
    title = models.CharField('Работа / задача', max_length=255)
    description = models.TextField('Описание', blank=True, default='')
    responsible = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plan_items', verbose_name='Ответственный',
    )
    deadline = models.DateField('Срок')
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    result = models.TextField('Результат / ход работы', blank=True, default='')
    task = models.ForeignKey(
        'tasks.Task', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plan_items', verbose_name='Задача',
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    completed_at = models.DateTimeField('Выполнено', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Пункт плана'
        verbose_name_plural = 'Пункты плана'
        ordering = ['order', 'deadline', 'id']

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return self.status in self.OPEN_STATUSES and self.deadline < timezone.localdate()

    def set_status(self, status):
        self.status = status
        if status == self.STATUS_DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif status != self.STATUS_DONE:
            self.completed_at = None

    def sync_from_task(self):
        """Подтягивает статус из связанной задачи. Возвращает True, если статус изменился."""
        from tasks.enums import TaskStatusEnum

        if not self.task_id or self.status == self.STATUS_CANCELLED:
            return False
        task_status = self.task.status
        if self.task.deleted_at:
            return False
        mapping = {
            TaskStatusEnum.COMPLETED.value[0]: self.STATUS_DONE,
            TaskStatusEnum.ACCEPTED.value[0]: self.STATUS_IN_PROGRESS,
            TaskStatusEnum.REVISION.value[0]: self.STATUS_IN_PROGRESS,
        }
        new_status = mapping.get(task_status)
        if new_status is None or new_status == self.status:
            return False
        self.set_status(new_status)
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        return True
