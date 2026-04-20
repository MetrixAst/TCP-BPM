from django.db import models
from django.db.models import Q
from django.http import Http404

from account.models import UserAccount, Notification
from project.utils import get_or_error, get_or_none
from .enums import TaskStatusEnum


class Task(models.Model):

    STATUSES = TaskStatusEnum.list()
    
    author = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, related_name="created_tasks", verbose_name="Автор", null=True, blank=True)
    responsible = models.ManyToManyField(UserAccount, related_name="responsible_tasks", verbose_name="Ответсвенные")
    observers = models.ManyToManyField(UserAccount, related_name="observe_tasks", verbose_name="Наблюдатели")

    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")
    deadline = models.DateField(verbose_name="Срок")
    status = models.SlugField("Статус", choices=STATUSES)

    title = models.CharField("Заголовок", max_length=120)
    text = models.TextField("Текст", max_length=2000, null=True, blank=True)

    important = models.BooleanField("Важная задача", default=False, blank=True)
    views = models.IntegerField("Просмотры", default=0)


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
            Q(responsible=request.user) | 
            Q(observers=request.user)
        )

        return queryset.distinct()
    
    @staticmethod
    def get_by_id(request, id, exception = True):
        
        qs = Task.get_available_queryset(request).filter(pk=id)
        if qs.count() > 0:
            if exception:
                return get_or_error(Task, id=id)
            return get_or_none(Task, id=id)
        else:
            if exception:
                raise Http404
            return None

    @property
    def status_info(self):
        return TaskStatusEnum.get_info(self.status)
    
    def get_status_notification(self):
        return TaskStatusEnum.get_notification_text(self.status)
    
    def actions(self, request):
        #TODO check can action
        return TaskStatusEnum.get_actions(self.status)
    
    def set_action(self, request, action):

        actions = self.actions(request)
        if action == "confirm":
            confirm_action = next((item for item in actions if item["action"] == "confirm"), None)
            if confirm_action is not None:
                self.status = confirm_action['next']
        elif action == "create":
            self.status = TaskStatusEnum.TO_DO.value[0]
            
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