from django.db import models
from django.conf import settings


class IdempotencyKey(models.Model):
    """
    Хранит результат обработки мутации по клиентскому ключу, чтобы повторная
    отправка (например, из офлайн-очереди мобильного приложения) не создавала
    дубликат записи, а возвращала тот же ответ, что и в первый раз.
    """
    key = models.CharField('Ключ', max_length=64)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='idempotency_keys',
    )
    endpoint = models.CharField('Эндпоинт', max_length=100)
    status_code = models.PositiveSmallIntegerField('HTTP статус ответа')
    response_body = models.JSONField('Тело ответа')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ключ идемпотентности'
        verbose_name_plural = 'Ключи идемпотентности'
        constraints = [
            models.UniqueConstraint(
                fields=['key', 'user', 'endpoint'],
                name='unique_idempotency_key_per_user_endpoint',
            ),
        ]

    def __str__(self):
        return f'{self.endpoint}:{self.key} ({self.user_id})'