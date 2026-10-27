"""Письма с логином/паролем портала арендатора."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def portal_login_url(request=None) -> str:
    path = reverse('account:auth')
    base = (getattr(settings, 'PUBLIC_SITE_URL', '') or '').rstrip('/')
    if base:
        return f'{base}{path}'
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def send_tenant_portal_credentials(
    *,
    tenant,
    username: str,
    password: str,
    created: bool,
    request=None,
) -> dict:
    """
    Отправляет арендатору письмо с логином и паролем.

    Возвращает {'sent': bool, 'error': str|None}.
    """
    to = (tenant.email or '').strip()
    if not to:
        return {'sent': False, 'error': 'У арендатора не указан email'}

    login_url = portal_login_url(request)
    room = tenant.number if getattr(tenant, 'number', None) else '—'
    action = 'создан' if created else 'обновлён (пароль сброшен)'
    subject = f'metriX BPM — доступ в портал ({tenant.name})'
    body = (
        f'Здравствуйте!\n\n'
        f'Для арендатора «{tenant.name}» (помещение {room}) {action} доступ в metriX BPM.\n\n'
        f'Вход: {login_url}\n'
        f'Логин: {username}\n'
        f'Пароль: {password}\n\n'
        f'Сохраните пароль в надёжном месте. При необходимости администратор может '
        f'сбросить его в карточке арендатора.\n\n'
        f'— metriX BPM\n'
    )

    try:
        sent = send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception('Failed to email portal credentials to %s', to)
        return {'sent': False, 'error': str(exc)}

    if not sent:
        return {'sent': False, 'error': 'send_mail вернул 0'}
    return {'sent': True, 'error': None}
