from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from mptt.models import MPTTModel, TreeForeignKey

from project.utils import PathAndRename, get_random_string

from .role_permissions import RoleEnums
from .tasks import send_notifications_task

from apps.hr.enums import EmployeeStatusEnum 
from django.core.exceptions import ValidationError

class UserAccount(AbstractUser):

    ROLES = [
        (RoleEnums.ADMINISTRATOR.value, 'Администратор'),
        (RoleEnums.STAFF.value, 'Сотрудник'),
        (RoleEnums.GUEST.value, 'Гость'),
    ]

    GENDERS = [
        ('male', 'Мужской'),
        ('female', 'Женский'),
    ]

    role = models.SlugField("Роль", choices=ROLES)
    avatar = models.FileField("Аватар", upload_to=PathAndRename("uploads/"), null=True, blank=True)

    birthday = models.DateField("Дата рождения", null=True, blank=True)
    gender = models.CharField("Пол", max_length=6, choices=GENDERS, null=True, blank=True)

    head = models.BooleanField("Руководитель компании", default=False, blank=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['username']

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return "/static/site/img/profile/profile-11.webp"
    
    def get_info(self):
        if(hasattr(self, 'employee_info')):
            return self.employee_info
        return None

    @property
    def get_name(self):
        if self.first_name is not None or self.last_name is not None:
            return " ".join([self.first_name, self.last_name])
        return self.username
    
    @staticmethod
    def create_guest():
        last_id = 15
        last = UserAccount.objects.filter(role=RoleEnums.GUEST.value).last()

        if last is not None:
            last_id = last.id + 1


        username = f"guest{last_id}"

        user = UserAccount.objects.create_user(
                                username=username,
                                email=username+'@test.kz',
                                password=get_random_string(),
                                role=RoleEnums.GUEST.value,
                                first_name=username,
                                )

        return user
    

class Department(MPTTModel):
    company = models.ForeignKey(
        'hr.Company',
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='departments',
        verbose_name="Компания"
    )
    LEVEL_TYPES = (
        ('department', 'Department'),
        ('division', 'Division'),
    )
    level_type = models.CharField(
        "Тип уровня",
        max_length=20, 
        choices=LEVEL_TYPES, 
        default='department'
    )
    
    name = models.CharField(verbose_name="Название", max_length=50)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')

    def __str__(self):
        return f"{self.name} ({self.company.name if self.company else '---'})"

    class MPTTMeta:
        order_insertion_by = ['name']
    
    class Meta:
        verbose_name = "Отдел"
        verbose_name_plural = "Отделы"
        unique_together = ('name', 'company')

    @property
    def get_head_info(self):
        res = {
            'name': self.name,
            'photo': "/static/site/img/profile/profile-11.webp",
            'job_title': 'Отдел',
        }
        head = self.employees.filter(head=True, status=EmployeeStatusEnum.ACTIVE).first()
        if head:
            res = {
                'name': head.user.get_name,
                'photo': head.user.get_avatar_url(),
                'job_title': head.position.title if head.position else 'Руководитель',
            }
        return res



class Employee(models.Model):
    user = models.OneToOneField(UserAccount, on_delete=models.CASCADE, related_name="employee_info")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="employees")
    iin = models.CharField("ИИН", max_length=12, unique=True, null=True, blank=True)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=EmployeeStatusEnum.choices,
        default=EmployeeStatusEnum.ACTIVE,
    )
    hire_date = models.DateField("Дата приема на работу", null=True, blank=True)
    supervisor = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='subordinates',
        verbose_name="Руководитель"
    )

    phone = models.CharField("Телефон", max_length=20, blank=True, default='')
    personal_email = models.EmailField("Личная почта", blank=True, null=True)

    position = models.ForeignKey(
        'hr.Position', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='employees',
        verbose_name="Должность"
    )

    head = models.BooleanField("Руководитель отдела", default=False)

    def clean(self):
        super().clean()
        if self.position and self.department:
            if self.position.department != self.department:
                raise ValidationError(
                    f"Должность '{self.position.title}' принадлежит отделу '{self.position.department.name}'. "
                    f"Вы не можете назначить её сотруднику из отдела '{self.department.name}'."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.username 
    
    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ['-head', 'user__last_name']

    def set_head(self):
        self.department.employees.all().filter(head=True).update(head=False)
        self.head = True
        self.save()




class PushToken(models.Model):
    user = models.ForeignKey(UserAccount, related_name='push_tokens', on_delete=models.CASCADE, null=False, blank=True)
    fcm = models.TextField("Токен", max_length=230, null=False)

    def __str__(self):
        return self.user.username

    class Meta:
        verbose_name = "Пуш токен"
        verbose_name_plural = "Пуш токены"
        ordering = ['-id']



class Notification(models.Model):
    title = models.CharField("Заголовок", max_length=140)
    text = models.CharField("Текст", max_length=300)
    created_date = models.DateTimeField(auto_now_add=True)

    users = models.ManyToManyField(UserAccount, blank=True, related_name='notifications', verbose_name="Пользователи")
    sended = models.BooleanField("Отправлен", default=False)

    target_id = models.IntegerField("Идентификатор объекта", null=True, blank=True)
    target_type = models.CharField("Тип объекта", null=True, blank=True, max_length=30)

    def __str__(self):
        if self.title == "":
            return self.text
        return self.title

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ['-id']

    
    @property
    def url(self):
        if self.target_type is not None:
            links = {
                'documents': reverse('documents:document', args=[self.target_id]),
                'purchases': reverse('documents:document', args=[self.target_id]),
                'budget': reverse('documents:document', args=[self.target_id]),
                'task': reverse('tasks:task', args=[self.target_id]),
            }

            return links.get(self.target_type, None)
        
        return None

    def send(self):
        send_notifications_task.delay(self.id)


    @staticmethod
    def create_for_document(document):
        users_qs = document.coordinators.all() | document.observers.all() | UserAccount.objects.filter(pk=document.author.pk)
        users_qs = users_qs.distinct()

        notification = Notification.objects.create(title="Добавлен документ", text="Новый документ", target_id=document.id, target_type=document.document_type)
        notification.users.add(*users_qs)


    @staticmethod
    def create_for_document(document):
        users_qs = document.coordinators.all() | document.observers.all() | UserAccount.objects.filter(pk=document.author.pk)
        users_qs = users_qs.distinct()

        text = document.get_status_notification()
        if text is None:
            text = {
                # 'title': 'Уведомление документа',
                'text': None,
            }

        notification = Notification.objects.create(title=document.title, text=text['text'], target_id=document.id, target_type=document.document_type)
        notification.users.add(*users_qs)


    @staticmethod
    def create_document_reminder(document):
        users_qs = document.coordinators.all() | document.observers.all() | UserAccount.objects.filter(pk=document.author.pk)
        users_qs = users_qs.distinct()
        
        today = timezone.now()
        
        days = (document.end_date - today).days

        if days == 0:
            text = "Срок действия документа истекает сегодня"
        elif days < 0:
            text = "Срок действия документа истек"
        else:
            text = f"До завершения срока документа осталось {days} дня"

        notification = Notification.objects.create(title=document.title, text=text, target_id=document.id, target_type=document.document_type)
        notification.users.add(*users_qs)
    
    @staticmethod
    def create_for_task(task):
        users_qs = task.co_executors.all() | task.observers.all()

        if task.executor:
            users_qs = users_qs | UserAccount.objects.filter(pk=task.executor.pk)

        if task.author:
            users_qs = users_qs | UserAccount.objects.filter(pk=task.author.pk)

        users_qs = users_qs.distinct()

        text = task.get_status_notification()
        if text is None:
            text = {
                'text': 'Уведомление задачи',
            }

        notification = Notification.objects.create(
            title=task.title,
            text=text['text'],
            target_id=task.id,
            target_type="task"
        )
        notification.users.add(*users_qs)

    @staticmethod
    def create_tenant_notify(tenant):
        users_qs = UserAccount.objects.filter(role__in=RoleEnums.tenant_roles())
        #TODO ADD TENANT ACCOUNT

        days = tenant.days
        text = "Срок аренды завершен" if days < 0 else f"До завершения срока аренды осталось {days} дней"

        notification = Notification.objects.create(title=tenant.name, text=text)
        notification.users.add(*users_qs)



@receiver(m2m_changed, sender=Notification.users.through)
def after_save_notification_m2m(signal, action, instance, **kwargs):
    if action == 'post_add':
        if not instance.sended:
            instance.sended = True
            instance.save()
            instance.send()



class NotificationIndicator(models.Model):
    user = models.ForeignKey(UserAccount, related_name='notification_indicator', on_delete=models.CASCADE, null=False, blank=True)
    target_id = models.IntegerField("Идентификатор объекта", null=True, blank=True)
    target_type = models.CharField("Тип объекта", null=True, blank=True, max_length=30)

    def __str__(self):
        return self.user.username

    class Meta:
        verbose_name = "Индикатор уведомлений"
        verbose_name_plural = "Индикаторы уведомлений"
        ordering = ['-id']

    @staticmethod
    def get_data(user):
        if user.is_authenticated:
            indicators = NotificationIndicator.objects.filter(user=user)
            counts = indicators.values('target_type').annotate(count=models.Count('id'))
            counts_dict = {item['target_type']: item['count'] for item in counts}

            res = list(indicators.values('target_id', 'target_type').distinct())

            return {
                'counts': counts_dict,
                'indicators': res,
            }
        return {
            'counts': {},
            'indicators': [],
        }
    
    @staticmethod
    def readed(user, target_id, target_type):
        indicator = NotificationIndicator.objects.filter(user=user, target_id=target_id, target_type=target_type)
        indicator.delete()