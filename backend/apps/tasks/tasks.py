from celery import shared_task
from django.utils import timezone
from datetime import timedelta


@shared_task(name='tasks.cleanup_bin')
def cleanup_bin(days=30):
    from tasks.models import Task

    cutoff = timezone.now() - timedelta(days=days)
    qs = Task.objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
    count = qs.count()
    qs.delete()
    return f'Удалено {count} задач из корзины старше {days} дней'