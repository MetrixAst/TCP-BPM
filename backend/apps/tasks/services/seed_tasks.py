"""Загрузка демо-задач."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from account.models import UserAccount
from tasks.demo_tasks import DEMO_TASKS
from tasks.enums import TaskStatusEnum
from tasks.models import Task, TaskHistory


def _pick_users():
    """Автор, исполнитель и наблюдатели из существующих учёток."""
    qs = UserAccount.objects.filter(is_active=True).order_by('id')
    users = list(qs[:6])
    if not users:
        return None, None, []
    author = users[0]
    executor = users[1] if len(users) > 1 else users[0]
    observers = users[2:5] if len(users) > 2 else [author]
    return author, executor, observers


def seed_demo_tasks(*, force: bool = False) -> dict:
    if not force and Task.objects.filter(title__in=[t[0] for t in DEMO_TASKS]).exists():
        return {
            'status': 'skipped',
            'reason': 'demo_exists',
            'count': Task.objects.count(),
        }

    author, executor, observers = _pick_users()
    if author is None:
        return {'status': 'error', 'error': 'no_users'}

    today = timezone.localdate()
    created = 0

    if force:
        Task.objects.filter(title__in=[t[0] for t in DEMO_TASKS]).delete()

    for title, text, status, priority, task_type, days_offset in DEMO_TASKS:
        if Task.objects.filter(title=title).exists():
            continue

        task = Task.objects.create(
            title=title,
            text=text,
            status=status,
            priority=priority,
            task_type=task_type,
            deadline=today + timedelta(days=days_offset),
            author=author,
            executor=executor,
        )

        task.observers.add(author, executor, *observers)
        if executor != author:
            task.co_executors.add(author)

        TaskHistory.objects.create(task=task, user=author, status=status)
        created += 1

    return {
        'status': 'ok',
        'created': created,
        'total': Task.objects.count(),
    }
