"""
Регистрация пользователей этого BPM в Metrix Auth Gateway.

Мобильное приложение входит через единый шлюз: пользователь вводит логин и
пароль, шлюз находит его сервер. Для этого BPM отправляет в шлюз отпечатки
логинов — HMAC-SHA256(AUTH_GATEWAY_LOGIN_SECRET, логин). Сами логины и
пароли в шлюз не уходят; пароль шлюз проверяет запросом к /api/token/ этого BPM.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(
        getattr(settings, 'AUTH_GATEWAY_URL', '')
        and getattr(settings, 'AUTH_GATEWAY_API_KEY', '')
        and getattr(settings, 'AUTH_GATEWAY_LOGIN_SECRET', '')
    )


def login_hash(login: str) -> str:
    """Должен совпадать с gateway.store.login_hash."""
    normalized = (login or '').strip().lower()
    return hmac.new(
        settings.AUTH_GATEWAY_LOGIN_SECRET.encode(), normalized.encode(), hashlib.sha256,
    ).hexdigest()


def mobile_logins() -> list[str]:
    from account.models import UserAccount

    users = UserAccount.objects.filter(is_active=True).exclude(password='').only('username', 'password')
    return [user.username for user in users if user.has_usable_password()]


def push_logins(session=None) -> int:
    """Полностью заменяет список логинов этого сервера в шлюзе. Возвращает их число."""
    if not is_configured():
        return 0
    hashes = [login_hash(login) for login in mobile_logins()]
    response = (session or requests).put(
        f"{settings.AUTH_GATEWAY_URL.rstrip('/')}/api/backend/logins",
        json={'logins': hashes},
        headers={'Authorization': f'Bearer {settings.AUTH_GATEWAY_API_KEY}'},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get('logins', len(hashes))
