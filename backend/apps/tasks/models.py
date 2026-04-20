from django.db import models
from django.db.models import Q
from django.http import Http404
from django.core.exceptions import PermissionDenied

from account.models import UserAccount, Notification
from project.utils import get_or_error, get_or_none
from .enums import TaskStatusEnum, PriorityEnum


class Task(models.Model):
    STATUSES = TaskStatusEnum.list()
    PRIORITIES = PriorityEnum.list()

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
    views = models.IntegerField("Просмотры", default=0)

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

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ['-id']

    @staticmethod
    def get_available_queryset(request):
        queryset = Task.objects.filter(
            Q(author=request.user) |
            Q(executor=request.user) |
            Q(co_executors=request.user) |
            Q(observers=request.user)
        )
        return queryset.distinct()

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
        available_actions = []

        for item in all_actions:
            action_name = item.get('action')

            if action_name == 'cancel':
                available_actions.append(item)
                continue

            transition = self.TRANSITIONS.get(self.status, {}).get(action_name)
            if not transition:
                continue

            if user_role in transition.get('roles', []):
                available_actions.append(item)

        return available_actions

    def set_action(self, request, action):
        if action == 'cancel':
            return

        if action == 'create':
            self.status = TaskStatusEnum.CREATED.value[0]
            self.save()
            TaskHistory.objects.create(task=self, user=request.user, status=self.status)
            Notification.create_for_task(self)
            return

        transition = self._check_action_permission(request.user, action)
        self.status = transition['next']
        self.save()

        TaskHistory.objects.create(task=self, user=request.user, status=self.status)
        Notification.create_for_task(self)

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

    def __str__(self):
        return self.task.title

    class Meta:
        verbose_name = "Активность"
        verbose_name_plural = "Активность"
        ordering = ['id']