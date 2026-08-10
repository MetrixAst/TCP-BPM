from django.db import models
from django.db.models import Q
from django.http import Http404
from django.core.exceptions import PermissionDenied

from decimal import Decimal

from django.core.validators import MinValueValidator

from account.models import UserAccount, Notification
from project.utils import get_or_error, get_or_none
from .enums import TaskStatusEnum, PriorityEnum, TaskTypeEnum
from django.utils import timezone


class Task(models.Model):
    STATUSES = TaskStatusEnum.list()
    PRIORITIES = PriorityEnum.list()
    TASK_TYPES = TaskTypeEnum.list()

    author = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        related_name="created_tasks",
        verbose_name="Автор",
        null=True,
        blank=True
    )

    executor = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        related_name="executed_tasks",
        verbose_name="Исполнитель",
        null=True,
        blank=True
    )

    co_executors = models.ManyToManyField(
        UserAccount,
        related_name="co_executed_tasks",
        verbose_name="Соисполнители",
        blank=True
    )

    observers = models.ManyToManyField(
        UserAccount,
        related_name="observe_tasks",
        verbose_name="Наблюдатели",
        blank=True
    )

    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")
    deadline = models.DateField(verbose_name="Срок")
    status = models.SlugField("Статус", choices=STATUSES)

    title = models.CharField("Заголовок", max_length=120)
    text = models.TextField("Текст", max_length=2000, null=True, blank=True)

    priority = models.SlugField("Приоритет", choices=PRIORITIES, default='medium')
    task_type = models.SlugField("Тип задачи", choices=TASK_TYPES, default='assignment')
    counterparty = models.ForeignKey(
        'onec.Counterparty',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name='Контрагент',
    )
    views = models.IntegerField("Просмотры", default=0)

    deleted_at = models.DateTimeField("Удалено в", null=True, blank=True)
    deleted_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="deleted_tasks",
        verbose_name="Кто удалил",
    )
    deleted_reason = models.CharField("Причина удаления", max_length=255, blank=True, default="")

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self, user, reason=""):
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.deleted_reason = reason
        self.save(update_fields=["deleted_at", "deleted_by", "deleted_reason"])
        self._notify_on_delete(user)

    def _notify_on_delete(self, deleted_by):
        try:
            from account.models import Notification
            users_to_notify = []
            if self.executor_id and self.executor_id != deleted_by.id:
                users_to_notify.append(self.executor_id)
            for obs in self.observers.exclude(id=deleted_by.id).values_list('id', flat=True):
                users_to_notify.append(obs)
            for co in self.co_executors.exclude(id=deleted_by.id).values_list('id', flat=True):
                users_to_notify.append(co)

            if not users_to_notify:
                return

            notification = Notification.objects.create(
                title=f'Задача удалена: {self.title}',
                text=f'Задача «{self.title}» была удалена. Причина: {self.deleted_reason or "не указана"}',
                target_id=self.id,
                target_type='task',
            )
            notification.users.add(*set(users_to_notify))
        except Exception:
            pass

    TRANSITIONS = {
        TaskStatusEnum.CREATED.value[0]: {
            'accept': {
                'next': TaskStatusEnum.ACCEPTED.value[0],
                'roles': ['executor', 'co_executor'],
            },
            'reject': {
                'next': TaskStatusEnum.REJECTED.value[0],
                'roles': ['executor'],
            },
        },
        TaskStatusEnum.ACCEPTED.value[0]: {
            'complete': {
                'next': TaskStatusEnum.COMPLETED.value[0],
                'roles': ['executor', 'co_executor'],
            },
        },
        TaskStatusEnum.COMPLETED.value[0]: {
            'revision': {
                'next': TaskStatusEnum.REVISION.value[0],
                'roles': ['author'],
            },
        },
        TaskStatusEnum.REVISION.value[0]: {
            'accept': {
                'next': TaskStatusEnum.ACCEPTED.value[0],
                'roles': ['executor', 'co_executor'],
            },
        },
        TaskStatusEnum.REJECTED.value[0]: {
            'reopen': {
                'next': TaskStatusEnum.CREATED.value[0],
                'roles': ['author'],
            },
        },
    }

    def can_delete(self, user):
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        from account.role_permissions import RoleEnums
        role = getattr(user, 'role', None)
        if hasattr(role, 'value'):
            role = role.value
        if role == RoleEnums.ADMINISTRATOR.value:
            return True
        if self.author_id == user.id:
            return True
        employee = getattr(user, 'employee_info', None)
        if employee and getattr(employee, 'head', False) and employee.department_id:
            from account.models import Employee
            dept_ids = list(
                employee.department.get_descendants(include_self=True).values_list('id', flat=True)
            )
            member_ids = list(
                Employee.objects.filter(department_id__in=dept_ids).values_list('user_id', flat=True)
            )
            if self.author_id in member_ids or self.executor_id in member_ids:
                return True
        return False

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.deleted_reason = ''
        self.save(update_fields=["deleted_at", "deleted_by", "deleted_reason"])



    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ['-id']

    @staticmethod
    def get_available_queryset(request):
        from account.role_permissions import RoleEnums

        user = request.user
        role = getattr(user, 'role', None)
        if hasattr(role, 'value'):
            role = role.value
        if getattr(user, 'is_superuser', False) or role == RoleEnums.ADMINISTRATOR.value:
            return Task.objects.filter(deleted_at__isnull=True)

        filters = (
            Q(author=user) |
            Q(executor=user) |
            Q(co_executors=user) |
            Q(observers=user)
        )

        employee = getattr(user, 'employee_info', None)
        if employee is not None and getattr(employee, 'head', False) and employee.department_id:
            from account.models import Employee
            dept_ids = list(
                employee.department.get_descendants(include_self=True).values_list('id', flat=True)
            )
            member_ids = list(
                Employee.objects.filter(department_id__in=dept_ids).values_list('user_id', flat=True)
            )
            if member_ids:
                filters |= (
                    Q(author_id__in=member_ids) |
                    Q(executor_id__in=member_ids) |
                    Q(co_executors__in=member_ids)
                )

        return Task.objects.filter(filters).distinct().filter(deleted_at__isnull=True)

    @staticmethod
    def get_by_id(request, id, exception=True):
        qs = Task.get_available_queryset(request).filter(pk=id)
        if qs.count() > 0:
            if exception:
                return get_or_error(Task, id=id)
            return get_or_none(Task, id=id)
        else:
            if exception:
                raise Http404
            return None

    def _get_user_role(self, user):
        if not user or not user.is_authenticated:
            return None

        if self.author_id == user.id:
            return 'author'
        if self.executor_id == user.id:
            return 'executor'
        if self.co_executors.filter(id=user.id).exists():
            return 'co_executor'
        if self.observers.filter(id=user.id).exists():
            return 'observer'

        return None

    def _get_transition(self, action):
        return self.TRANSITIONS.get(self.status, {}).get(action)

    def _check_action_permission(self, user, action):
        transition = self._get_transition(action)
        if not transition:
            raise PermissionDenied("Недоступное действие для текущего статуса.")

        # Админ задач (суперюзер/администратор) может выполнять любой переход —
        # так же, как при перетаскивании на канбане.
        if self._user_is_tasks_admin(user):
            return transition

        user_role = self._get_user_role(user)
        allowed_roles = transition.get('roles', [])

        if user_role not in allowed_roles:
            raise PermissionDenied("У вас нет прав на выполнение этого действия.")

        return transition

    @property
    def status_info(self):
        return TaskStatusEnum.get_info(self.status)

    def get_status_notification(self):
        return TaskStatusEnum.get_notification_text(self.status)

    def actions(self, request):
        all_actions = TaskStatusEnum.get_actions(self.status) or []
        user_role = self._get_user_role(request.user)
        is_admin = self._user_is_tasks_admin(request.user)
        available_actions = []

        for item in all_actions:
            action_name = item.get('action')

            if action_name == 'cancel':
                available_actions.append(item)
                continue

            transition = self.TRANSITIONS.get(self.status, {}).get(action_name)
            if not transition:
                continue

            # Админ видит все переходы (как на канбане); остальные — по своей роли.
            if is_admin or user_role in transition.get('roles', []):
                available_actions.append(item)

        return available_actions

    @staticmethod
    def _notify_participants(task):
        try:
            Notification.create_for_task(task)
        except Exception:
            pass

    @staticmethod
    def _user_is_tasks_admin(user):
        from account.role_permissions import RoleEnums

        if not user or not user.is_authenticated:
            return False
        role = getattr(user, 'role', None)
        if hasattr(role, 'value'):
            role = role.value
        return getattr(user, 'is_superuser', False) or role == RoleEnums.ADMINISTRATOR.value

    def set_action(self, request, action):
        if action == 'cancel':
            return

        if action == 'create':
            self.status = TaskStatusEnum.CREATED.value[0]
            self.save()
            TaskHistory.objects.create(task=self, user=request.user, status=self.status)
            self._notify_participants(self)
            return

        transition = self._check_action_permission(request.user, action)
        self.status = transition['next']
        self.save()

        TaskHistory.objects.create(task=self, user=request.user, status=self.status)
        self._notify_participants(self)

    def transition_to_status(self, request, new_status):
        """Смена статуса через допустимый transition (для канбана)."""
        if self.status == new_status:
            return None

        if self._user_is_tasks_admin(request.user):
            self.status = new_status
            self.save(update_fields=['status'])
            TaskHistory.objects.create(task=self, user=request.user, status=self.status)
            self._notify_participants(self)
            return 'admin'

        for action, transition in self.TRANSITIONS.get(self.status, {}).items():
            if transition.get('next') == new_status:
                self.set_action(request, action)
                return action
        raise PermissionDenied('Недопустимый переход статуса.')

    @staticmethod
    def get_statistic(request):
        tasks = Task.get_available_queryset(request)
        statuses = TaskStatusEnum.list()

        res = []
        for current in statuses:
            res.append({
                'slug': current[0],
                'title': current[1],
                'count': tasks.filter(status=current[0]).count(),
                'icon': TaskStatusEnum.get_info(current[0]).get('icon')
            })

        return res


class TaskHistory(models.Model):

    STATUSES = TaskStatusEnum.list()

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history", verbose_name="Задача")
    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Пользователь", null=True, blank=True)
    status = models.SlugField("Статус", choices=STATUSES)
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")


    @property
    def title(self):
        return TaskStatusEnum.from_value(self.status)[1]

    @property
    def status_info(self):
        return TaskStatusEnum.get_info(self.status)

    def __str__(self):
        return self.task.title

    class Meta:
        verbose_name = "Активность"
        verbose_name_plural = "Активность"
        ordering = ['id']

class TaskFile(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Задача"
    )
    file = models.FileField(
        upload_to="tasks/files/",
        verbose_name="Файл"
    )
    uploaded_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Загрузил"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Файл задачи"
        verbose_name_plural = "Файлы задач"
        ordering = ["-id"]

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name)

    def __str__(self):
        return self.file.name


class TaskChecklistItem(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='checklist_items',
        verbose_name='Задача',
    )
    title = models.CharField('Пункт', max_length=255)
    is_done = models.BooleanField('Выполнено', default=False)
    sort_order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Пункт чеклиста'
        verbose_name_plural = 'Чеклист задачи'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title


class TaskLineItem(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='line_items',
        verbose_name='Задача',
    )
    name = models.CharField('Наименование', max_length=255)
    quantity = models.DecimalField(
        'Количество',
        max_digits=12,
        decimal_places=2,
        default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    unit = models.CharField('Ед. изм.', max_length=20, blank=True, default='шт')
    price = models.DecimalField(
        'Цена',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
    )

    class Meta:
        verbose_name = 'Позиция задачи'
        verbose_name_plural = 'Позиции задачи'
        ordering = ['id']

    @property
    def total(self):
        return self.quantity * self.price

    def __str__(self):
        return self.name


class TaskUserFlag(models.Model):
    """Персональные пометки пользователя на задаче (например «избранное»).

    Заменяет хранение в localStorage: состояние больше не растёт в браузере,
    а живёт в БД по паре (пользователь, задача, флаг).
    """

    FAVORITE = 'favorite'
    FLAG_CHOICES = [
        (FAVORITE, 'Избранное'),
    ]

    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name='task_flags',
        verbose_name='Пользователь',
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='user_flags',
        verbose_name='Задача',
    )
    flag = models.SlugField('Флаг', choices=FLAG_CHOICES, default=FAVORITE)
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Пометка задачи'
        verbose_name_plural = 'Пометки задач'
        unique_together = ('user', 'task', 'flag')
        ordering = ['-id']

    def __str__(self):
        return f'{self.user_id}:{self.task_id}:{self.flag}'