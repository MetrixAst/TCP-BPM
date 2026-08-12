from django.db import models
from django.db.models import Q
from django.http import Http404
from django.core.exceptions import ValidationError
from project.utils import PathAndRename
from account.models import UserAccount, Department
from account.role_permissions import RoleEnums, RolePermissions, PermissionEnums

from .enums import (
    TicketCategoryEnum,
    TicketPriorityEnum,
    TicketStatusEnum,
    TICKET_TRANSITIONS,
)


def user_is_manager(user):
    """Сотрудник, обрабатывающий сервисные заявки (не портальный арендатор)."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    role = user.role
    if role in RoleEnums.portal_roles():
        return False
    return RolePermissions.checkPermission(role, PermissionEnums.SERVICE_REQUESTS)


class ServiceRequest(models.Model):
    """Сервисная заявка от арендатора БЦ (поломка/обслуживание)."""

    CATEGORIES = TicketCategoryEnum.list()
    PRIORITIES = TicketPriorityEnum.list()
    STATUSES = TicketStatusEnum.list()

    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_requests', verbose_name='Арендатор',
    )
    author = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_service_requests', verbose_name='Заявитель',
    )

    category = models.SlugField('Категория', choices=CATEGORIES, default=TicketCategoryEnum.OTHER.value[0])
    title = models.CharField('Тема', max_length=160)
    description = models.TextField('Описание проблемы', max_length=3000)
    room = models.CharField('Помещение / локация', max_length=60, null=True, blank=True)
    photo = models.ImageField('Фото', upload_to=PathAndRename('tickets/'), null=True, blank=True)

    priority = models.SlugField('Приоритет', choices=PRIORITIES, default=TicketPriorityEnum.MEDIUM.value[0])
    status = models.SlugField('Статус', choices=STATUSES, default=TicketStatusEnum.NEW.value[0])

    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_requests', verbose_name='Отдел',
    )
    assignee = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_service_requests', verbose_name='Ответственный',
    )

    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Сервисная заявка'
        verbose_name_plural = 'Сервисные заявки'
        ordering = ['-id']

    def __str__(self):
        return f'Заявка №{self.id} — {self.title}'

    # ---- display helpers -------------------------------------------------

    @property
    def status_info(self):
        return TicketStatusEnum.get_info(self.status)

    @property
    def priority_info(self):
        return TicketPriorityEnum.get_info(self.priority)

    @property
    def number(self):
        return f'SR-{self.id:05d}' if self.id else 'SR-—'

    # ---- access ----------------------------------------------------------

    @staticmethod
    def get_available_queryset(request):
        user = request.user
        base = ServiceRequest.objects.select_related(
            'tenant', 'author', 'assignee', 'department',
        )
        if user_is_manager(user):
            return base
        # портальный арендатор/гость видит только свои заявки
        return base.filter(Q(author=user) | Q(tenant__portal_users=user)).distinct()

    @staticmethod
    def get_by_id(request, pk, exception=True):
        obj = ServiceRequest.get_available_queryset(request).filter(pk=pk).first()
        if obj is None and exception:
            raise Http404
        return obj

    def can_manage(self, user):
        return user_is_manager(user)

    def is_author(self, user):
        if not user or not user.is_authenticated:
            return False
        if self.author_id and self.author_id == user.id:
            return True
        return bool(self.tenant_id and getattr(user, 'tenant_id', None) == self.tenant_id)

    # ---- workflow --------------------------------------------------------

    def _user_role(self, user):
        if self.can_manage(user):
            return 'manager'
        if self.is_author(user):
            return 'author'
        return None

    def actions(self, request):
        """Список доступных пользователю действий для текущего статуса."""
        role = self._user_role(request.user)
        if role is None:
            return []
        result = []
        for action, cfg in TICKET_TRANSITIONS.get(self.status, {}).items():
            if role in cfg['roles']:
                result.append({
                    'action': action,
                    'title': cfg['title'],
                    'next': cfg['next'],
                    'variant': cfg.get('variant', 'primary'),
                })
        return result

    def apply_action(self, request, action, comment='', assignee=None):
        """Применяет переход статуса, если он разрешён пользователю."""
        allowed = {a['action']: a for a in self.actions(request)}
        if action not in allowed:
            return False, 'Действие недоступно'

        if action == 'accept' and not self.assignee and not assignee:
            return False, 'Выберите исполнителя перед принятием заявки'

        if action == 'accept' and assignee:
            self.assignee = assignee

        self.status = allowed[action]['next']
        fields = ['status', 'updated_at']
        if action == 'accept' and assignee:
            fields.append('assignee')
        self.save(update_fields=fields)

        ServiceRequestHistory.objects.create(
            request=self, user=request.user, status=self.status,
            comment=comment or '',
        )
        from .services import notify_ticket_status
        notify_ticket_status(self, actor=request.user)
        if action == 'accept' and assignee:
            from .services import notify_ticket_assigned
            notify_ticket_assigned(self, actor=request.user)
        return True, None

    def assign(self, request, department=None, assignee=None, priority=None, comment=''):
        """Маршрутизация заявки: отдел / ответственный / приоритет (только сотрудник)."""
        if not self.can_manage(request.user):
            return False
        changed = []
        if department is not None and department != self.department:
            self.department = department
            changed.append('department')
        if assignee is not None and assignee != self.assignee:
            self.assignee = assignee
            changed.append('assignee')
        if priority and priority != self.priority:
            self.priority = priority
            changed.append('priority')
        if not changed:
            return False
        changed.append('updated_at')
        self.save(update_fields=changed)
        dept_name = self.department.name if self.department else '—'
        assignee_name = self.assignee.get_name if self.assignee else '—'
        ServiceRequestHistory.objects.create(
            request=self, user=request.user, status=self.status,
            comment=comment or f'Маршрутизация: отдел «{dept_name}», ответственный «{assignee_name}».',
        )
        from .services import notify_ticket_assigned
        notify_ticket_assigned(self, actor=request.user)
        return True

    def get_data(self):
        return {
            'Номер': self.number,
            'Категория': self.get_category_display(),
            'Приоритет': self.get_priority_display(),
            'Статус': self.get_status_display(),
            'Помещение': self.room,
            'Арендатор': str(self.tenant) if self.tenant else None,
            'Заявитель': self.author.get_name if self.author else None,
            'Отдел': self.department.name if self.department else None,
            'Ответственный': self.assignee.get_name if self.assignee else None,
            'Создано': self.created_at,
        }


class ServiceRequestHistory(models.Model):
    request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name='history', verbose_name='Заявка',
    )
    user = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Пользователь',
    )
    status = models.SlugField('Статус', choices=ServiceRequest.STATUSES)
    comment = models.TextField('Комментарий', null=True, blank=True)
    created_at = models.DateTimeField('Дата', auto_now_add=True)

    class Meta:
        verbose_name = 'История сервисной заявки'
        verbose_name_plural = 'История сервисных заявок'
        ordering = ['-id']

    def __str__(self):
        return f'{self.request_id}:{self.status}'

    @property
    def status_info(self):
        return TicketStatusEnum.get_info(self.status)

class TicketMessage(models.Model):
    """Сообщение в чате заявки между арендатором и исполнителем/менеджером."""

    request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name='messages', verbose_name='Заявка',
    )
    author = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Автор',
    )
    text = models.TextField('Текст', max_length=2000)
    created_at = models.DateTimeField('Дата', auto_now_add=True)

    class Meta:
        verbose_name = 'Сообщение заявки'
        verbose_name_plural = 'Сообщения заявок'
        ordering = ['id']

    def __str__(self):
        return f'{self.request_id}: {self.text[:30]}'

    @staticmethod
    def can_view(ticket, user):
        """Арендатор видит чат своей заявки; исполнитель/менеджер — назначенных."""
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if ticket.is_author(user):
            return True
        if ticket.assignee_id and ticket.assignee_id == user.id:
            return True
        if user_is_manager(user):
            return True
        return False

class TicketAttachment(models.Model):
    request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name='attachments', verbose_name='Заявка',
    )
    file = models.FileField('Файл', upload_to=PathAndRename('tickets/attachments/'))
    original_name = models.CharField('Оригинальное имя файла', max_length=255, blank=True, default='')
    uploaded_by = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Загрузил',
    )
    created_at = models.DateTimeField('Дата', auto_now_add=True)

    class Meta:
        verbose_name = 'Вложение заявки'
        verbose_name_plural = 'Вложения заявок'
        ordering = ['id']

    def __str__(self):
        return self.filename

    @property
    def filename(self):
        return self.file.name.split('/')[-1] if self.file else ''

    @property
    def is_image(self):
        ext = self.filename.rsplit('.', 1)[-1].lower() if '.' in self.filename else ''
        return ext in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp')

    @staticmethod
    def can_view(ticket, user):
        return TicketMessage.can_view(ticket, user)

    @property
    def display_name(self):
        """Показываем оригинальное имя если есть, иначе хэш"""
        return self.original_name if self.original_name else self.filename

class TicketTypeConfig(models.Model):
    ticket_type = models.CharField('Тип заявки', max_length=64, choices=TicketCategoryEnum.list())
    department = models.ForeignKey(
        'account.Department',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='ticket_type_configs',
        verbose_name='Отдел',
        help_text='Пусто — настройка действует для всех отделов по умолчанию.',
    )
    requires_approval = models.BooleanField('Требует согласования', default=False)
    sla_hours = models.PositiveIntegerField(
        'SLA, часов',
        null=True, blank=True,
        help_text='Срок на обработку заявки этого типа. Пусто — SLA не задан.',
    )
    auto_assign_to = models.ForeignKey(
        'account.UserAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='auto_assigned_tickets',
        verbose_name='Автоназначение на',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Настройка типа заявки'
        verbose_name_plural = 'Настройки типов заявок'
        constraints = [
            models.UniqueConstraint(
                fields=['ticket_type', 'department'],
                name='unique_tickettypeconfig_type_department',
            )
        ]
        ordering = ['ticket_type', 'department_id']

    def clean(self):
        super().clean()
        if self.sla_hours is not None and self.sla_hours <= 0:
            raise ValidationError('SLA должен быть положительным числом часов.')

        if self.requires_approval and self.department_id:
            from account.models import Employee
            has_head = Employee.objects.filter(
                department_id=self.department_id, head=True, status='active',
            ).exists()
            if not has_head:
                raise ValidationError(
                    f'В отделе «{self.department}» нет активного руководителя — '
                    f'согласование по умолчанию перейдёт администратору. '
                    f'Назначьте руководителя отдела или отключите обязательное согласование.'
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        dept = self.department.name if self.department else 'все отделы'
        return f"{self.ticket_type} / {dept} (согласование: {self.requires_approval})"


class ApprovalDecision(models.Model):
    DECISION_APPROVE = 'approve'
    DECISION_REJECT = 'reject'
    DECISION_CHOICES = [
        (DECISION_APPROVE, 'Согласовано'),
        (DECISION_REJECT, 'Отклонено'),
    ]

    ticket = models.ForeignKey(
        'ServiceRequest',
        on_delete=models.CASCADE,
        related_name='approval_decisions',
        verbose_name='Заявка',
    )
    actor = models.ForeignKey(
        'account.UserAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approval_actions',
        verbose_name='Кто принял решение',
    )
    decision = models.CharField('Решение', max_length=16, choices=DECISION_CHOICES)
    comment = models.TextField('Комментарий', blank=True, default='')
    ip_address = models.GenericIPAddressField('IP адрес', null=True, blank=True)
    created_at = models.DateTimeField('Время', auto_now_add=True)

    class Meta:
        verbose_name = 'Решение по согласованию'
        verbose_name_plural = 'Решения по согласованию'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket} | {self.decision} | {self.actor}"
 