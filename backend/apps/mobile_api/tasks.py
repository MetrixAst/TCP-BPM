import logging

from celery import shared_task
from django.core.management import call_command
from django.core.management.base import CommandError

logger = logging.getLogger(__name__)


@shared_task(name='mobile_api.refresh_review_demo')
def refresh_review_demo(username='appreview'):
    """Переносит демо-данные проверяющего на текущий день.

    Обходы, отметки и прогресс привязаны к дате, поэтому уже назавтра
    аккаунт App Review выглядит пустым и расходится со скриншотами — это
    ровно то, за что приложение отклонили по 2.3.3. Аккаунта может не
    быть (например, на стенде), и это не повод ронять задачу.
    """
    try:
        call_command('seed_review_demo', username=username)
    except CommandError as error:
        logger.warning('Демо-данные для %s не обновлены: %s', username, error)
        return f'пропущено: {error}'
    return f'демо-данные обновлены для {username}'
