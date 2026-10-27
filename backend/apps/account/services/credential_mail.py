"""Письма с новым логином и паролем. Пароль в ответ интерфейса не попадает."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def login_url(request=None) -> str:
    path = reverse('account:auth')
    base = (getattr(settings, 'PUBLIC_SITE_URL', '') or '').rstrip('/')
    if base:
        return f'{base}{path}'
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def send_password_reset_email(*, user, password: str, request=None) -> None:
    to = (user.email or '').strip()
    if not to:
        raise ValueError('У пользователя не указан email')

    subject = 'metriX BPM — новый пароль'
    body = (
        f'Здравствуйте!\n\n'
        f'Администратор сбросил пароль вашей учётной записи metriX BPM.\n\n'
        f'Вход: {login_url(request)}\n'
        f'Логин: {user.username}\n'
        f'Пароль: {password}\n\n'
        f'Сохраните пароль. После входа его можно сменить в профиле.\n\n'
        f'— metriX BPM\n'
    )
    sent = send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to],
        fail_silently=False,
    )
    if not sent:
        raise RuntimeError('send_mail вернул 0')
    logger.info('password_reset_email_sent user=%s to=%s', user.pk, to)
