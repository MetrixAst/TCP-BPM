"""Создаёт демо-исполнителя с назначенными задачами."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import UserAccount
from account.role_permissions import RoleEnums
from tasks.enums import TaskStatusEnum
from tasks.models import Task, TaskHistory


class Command(BaseCommand):
    help = 'Создаёт пользователя demo_executor с задачами в статусе «Создана» и «Принята»'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='Trc2026!', help='Пароль пользователя')
        parser.add_argument('--username', default='demo_executor', help='Логин')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        author = UserAccount.objects.filter(role=RoleEnums.ADMINISTRATOR.value).first()
        if not author:
            author = UserAccount.objects.filter(is_active=True).first()
        if not author:
            self.stderr.write(self.style.ERROR('Нет пользователей в системе'))
            return

        user, created = UserAccount.objects.get_or_create(
            username=username,
            defaults={
                'role': RoleEnums.STAFF.value,
                'first_name': 'Демо',
                'last_name': 'Исполнитель',
                'email': f'{username}@trc.local',
                'is_active': True,
            },
        )
        user.set_password(password)
        user.save()

        today = timezone.localdate()
        specs = [
            ('Проверить реестр оплат', 'Сверить платежи за текущую неделю', TaskStatusEnum.CREATED.value[0], 3),
            ('Подготовить отчёт по задачам', 'Краткая сводка для руководителя', TaskStatusEnum.CREATED.value[0], 5),
            ('Согласовать документ с контрагентом', 'Договор поставки', TaskStatusEnum.ACCEPTED.value[0], 7),
            ('Обновить карточку сотрудника', 'Проверить данные в HR', TaskStatusEnum.ACCEPTED.value[0], 2),
            ('Закрыть заявку в поддержке', 'Ответить арендатору', TaskStatusEnum.CREATED.value[0], 1),
        ]

        added = 0
        for title, text, status, days in specs:
            if Task.objects.filter(title=title, executor=user).exists():
                continue
            task = Task.objects.create(
                title=title,
                text=text,
                status=status,
                priority='medium',
                task_type='assignment',
                deadline=today + timedelta(days=days),
                author=author,
                executor=user,
            )
            task.observers.add(author)
            TaskHistory.objects.create(task=task, user=author, status=status)
            added += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Пользователь: {username} / пароль: {password} '
                f'({"создан" if created else "уже был"}). Добавлено задач: {added}.',
            )
        )
