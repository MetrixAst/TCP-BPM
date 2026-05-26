"""Фабрика HTTP-клиента 1С."""

from __future__ import annotations

from django.conf import settings

from onec.client_1c.client import Client1C


class OneCNotConfiguredError(RuntimeError):
    pass


def is_onec_configured() -> bool:
    return bool(
        getattr(settings, 'ONE_C_BASE_URL', '')
        and getattr(settings, 'ONE_C_API_USER', '')
        and getattr(settings, 'ONE_C_API_PASSWORD', '')
    )


def get_onec_client() -> Client1C:
    if not is_onec_configured():
        raise OneCNotConfiguredError(
            'Задайте ONE_C_BASE_URL, ONE_C_API_USER и ONE_C_API_PASSWORD в .env'
        )
    client = Client1C(
        base_url=settings.ONE_C_BASE_URL,
        basic_auth_user=settings.ONE_C_BASIC_AUTH_USER,
        basic_auth_password=settings.ONE_C_BASIC_AUTH_PASSWORD,
        api_user=settings.ONE_C_API_USER,
        api_password=settings.ONE_C_API_PASSWORD,
        timeout=getattr(settings, 'ONE_C_TIMEOUT', 30),
        verify_ssl=getattr(settings, 'ONE_C_VERIFY_SSL', True),
    )
    client.authenticate()
    return client
