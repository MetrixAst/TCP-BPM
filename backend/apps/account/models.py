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

from hr.enums import EmployeeStatusEnum 

from django.core.exceptions import ValidationError

class UserAccount(AbstractUser):

    ROLES = [
        (RoleEnums.ADMINISTRATOR.value, 'Администратор'),
        (RoleEnums.HR.value, 'HR-менеджер'),
        (RoleEnums.STAFF.value, 'Сотрудник'),
        (RoleEnums.GUEST.value, 'Гость'),
        (RoleEnums.TENANT.value, 'Арендатор'),
        (RoleEnums.OWNER.value, 'Владелец'),
        (RoleEnums.CFO.value, 'Финансовый директор'),
        (RoleEnums.CHIEF_ACCOUNTANT.value, 'Главный бухгалтер'),
    ]

    GENDERS = [
        ('male', 'Мужской'),
        ('female', 'Женский'),
    ]

    role = models.SlugField("Роль", choices=ROLES)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_users',
        verbose_name='Арендатор',
    )
    avatar = models.FileField("Аватар", upload_to=PathAndRename("uploads/"), null=True, blank=True)

    birthday = models.DateField("Дата рождения", null=True, blank=True)
    gender = models.CharField("Пол", max_length=6, choices=GENDERS, null=True, blank=True)

    head = models.BooleanField("Руководитель компании", default=False, blank=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['username']

    def has_app_permission(self, permission):
        from account.services.permissions import user_has_permission
        return user_has_permission(self, permission)

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
        parts = []
        for attr in ('first_name', 'last_name'):
            val = getattr(self, attr, None)
            if val and str(val).strip():
                parts.append(str(val).strip())
        if parts:
            return ' '.join(parts)
        return self.username or ''

    def __str__(self):
        name = self.get_name
        if name and name != self.username:
            return name
        return self.username or f'User #{self.pk}'
    
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

    @staticmethod
    def create_tenant_user(tenant, username=None):
        email = (getattr(tenant, 'email', '') or '').strip().lower()
        base = (username or email or f"tenant{tenant.pk}").strip().lower()
        username = base
        suffix = 1
        while UserAccount.objects.filter(username=username).exists():
            username = f"{base}_{suffix}"
            suffix += 1

        user = UserAccount.objects.create_user(
            username=username,
            email=(email or f"{username}@tenant.local"),
            password=get_random_string(),
            role=RoleEnums.TENANT.value,
            first_name=tenant.name[:30],
            tenant=tenant,
        )
        return user

    @property
    def is_portal_user(self):
        return self.role in RoleEnums.portal_roles()


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


class AccessScope(models.Model):

    name = models.CharField('Название', max_length=120)
    description = models.TextField('Описание', blank=True)
    is_global = models.BooleanField(
        'Доступен всем авторизованным',
        default=False,
        help_text='Если включено — контрагенты этого типа видят все пользователи.',
    )
    roles = models.JSONField(
        'Роли',
        default=list,
        blank=True,
        help_text='Список slug ролей (administrator, staff, …).',
    )
    departments = models.ManyToManyField(
        Department,
        blank=True,
        verbose_name='Отделы',
        related_name='access_scopes',
    )
    users = models.ManyToManyField(
        UserAccount,
        blank=True,
        verbose_name='Пользователи',
        related_name='access_scopes',
    )

    class Meta:
        verbose_name = 'Зона доступа'
        verbose_name_plural = 'Зоны доступа'
        ordering = ['name']

    def __str__(self):
        return self.name

    def is_unrestricted(self):
        if self.is_global:
            return True
        if self.roles:
            return False
        if self.departments.exists():
            return False
        if self.users.exists():
            return False
        return True


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

        if self.iin:
            if not self.iin.isdigit() or len(self.iin) != 12:
                raise ValidationError('ИИН должен содержать ровно 12 цифр.')
            
            qs = Employee.objects.filter(iin=self.iin)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(f'Сотрудник с ИИН {self.iin} уже существует.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_display_name(self):
        if self.user_id:
            name = (self.user.get_name or '').strip()
            if name and name != self.user.username:
                return name
            return self.user.username
        return '—'

    def get_display_with_position(self):
        label = self.get_display_name()
        if self.position_id:
            return f'{label} — {self.position.title}'
        return label

    def __str__(self):
        return self.get_display_with_position()
    
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
                'requistion': reverse('requistions:item', args=[self.target_id]),
                'ticket': reverse('tickets:item', args=[self.target_id]),
            }

            return links.get(self.target_type, None)
        
        return None

    def send(self):
        try:
            send_notifications_task.delay(self.id)
        except Exception:
            try:
                send_notifications_task(self.id)
            except Exception:
                pass


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
        users_qs = task.observers.all()
        if task.executor_id:
            users_qs = users_qs | UserAccount.objects.filter(pk=task.executor_id)
        users_qs = users_qs | task.co_executors.all()
        if task.author_id:
            users_qs = users_qs | UserAccount.objects.filter(pk=task.author_id)
        users_qs = users_qs.distinct()

        text = task.get_status_notification()
        if text is None:
            text = {
                # 'title': document,
                'text': 'Уведомление задачи',
            }

        notification = Notification.objects.create(title=task.title, text=text['text'], target_id=task.id, target_type="task")
        notification.users.add(*users_qs)

    @staticmethod
    def create_tenant_notify(tenant):
        internal_qs = UserAccount.objects.filter(role__in=RoleEnums.tenant_roles())
        tenant_qs = UserAccount.objects.filter(
            role=RoleEnums.TENANT.value,
            tenant=tenant,
        )
        users_qs = (internal_qs | tenant_qs).distinct()

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

from account.models_rbac import (  
    AppPermission,
    PermissionProfile,
    UserPermissionOverride,
)

class EmployeeStatusLog(models.Model):
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='status_logs',
        verbose_name='Сотрудник',
    )
    actor = models.ForeignKey(
        'UserAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='status_change_actions',
        verbose_name='Кто изменил',
    )
    old_status = models.CharField('Старый статус', max_length=32)
    new_status = models.CharField('Новый статус', max_length=32)
    reason = models.CharField('Причина', max_length=255, blank=True, default='')
    ip_address = models.GenericIPAddressField('IP адрес', null=True, blank=True)
    created_at = models.DateTimeField('Время', auto_now_add=True)

    class Meta:
        app_label = 'account'
        verbose_name = 'Лог изменения статуса'
        verbose_name_plural = 'Логи изменения статуса'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.employee} | {self.old_status} → {self.new_status} | {self.created_at}"

class NotificationUser(models.Model):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='notification_users',
    )
    user = models.ForeignKey(
        'UserAccount',
        on_delete=models.CASCADE,
        related_name='notification_users',
    )
    is_read = models.BooleanField('Прочитано', default=False)
    read_at = models.DateTimeField('Время прочтения', null=True, blank=True)

    class Meta:
        unique_together = [('notification', 'user')]
        verbose_name = 'Уведомление пользователя'
        verbose_name_plural = 'Уведомления пользователей'