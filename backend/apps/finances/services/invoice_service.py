"""
HTTP-клиент сервиса счетов (invoice/, FastAPI).

BPM ходит в сервис под служебным админом сервиса; JWT кешируется.
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = 'invoice_service:token'
TOKEN_CACHE_TTL = 12 * 60 * 60


class InvoiceServiceError(Exception):
    """Сервис отказал или недоступен; str(exc) можно показывать пользователю."""


def is_configured() -> bool:
    return bool(
        settings.INVOICE_SERVICE_URL
        and settings.INVOICE_SERVICE_USERNAME
        and settings.INVOICE_SERVICE_PASSWORD
        and settings.INVOICE_SERVICE_TENANT_ID
    )


def _url(path: str) -> str:
    return f"{settings.INVOICE_SERVICE_URL.rstrip('/')}{path}"


def _login() -> str:
    try:
        resp = requests.post(
            _url('/api/admin/auth/login'),
            json={
                'username': settings.INVOICE_SERVICE_USERNAME,
                'password': settings.INVOICE_SERVICE_PASSWORD,
            },
            timeout=settings.INVOICE_SERVICE_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise InvoiceServiceError('Сервис счетов недоступен') from exc
    if resp.status_code != 200:
        logger.error('invoice_service_login_failed: status=%s', resp.status_code)
        raise InvoiceServiceError('Не удалось войти в сервис счетов')
    token = resp.json()['access_token']
    cache.set(TOKEN_CACHE_KEY, token, TOKEN_CACHE_TTL)
    return token


def _request(method: str, path: str, **kwargs) -> requests.Response:
    token = cache.get(TOKEN_CACHE_KEY) or _login()
    for attempt in (1, 2):
        try:
            resp = requests.request(
                method,
                _url(path),
                headers={'Authorization': f'Bearer {token}'},
                timeout=settings.INVOICE_SERVICE_TIMEOUT,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise InvoiceServiceError('Сервис счетов недоступен') from exc
        if resp.status_code == 401 and attempt == 1:
            cache.delete(TOKEN_CACHE_KEY)
            token = _login()
            continue
        return resp
    return resp


def _error_detail(resp: requests.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f'HTTP {resp.status_code}'
    detail = body.get('detail') or body.get('message')
    return detail if isinstance(detail, str) else f'HTTP {resp.status_code}'


def send_file_via_whatsapp(
    *,
    phone: str,
    counterparty_id: str,
    file_name: str,
    file_bytes: bytes,
    invoice_number: str | None = None,
) -> None:
    """Отправляет файл контрагенту в WhatsApp. Бросает InvoiceServiceError при отказе."""
    data = {
        'phone_number': phone,
        'counterparty_id': counterparty_id,
        'tenant_id': str(settings.INVOICE_SERVICE_TENANT_ID),
    }
    if invoice_number:
        data['invoice_id'] = invoice_number
    resp = _request(
        'POST',
        '/api/notifications/send-file',
        data=data,
        files={'file': (file_name, file_bytes, 'application/pdf')},
    )
    if resp.status_code != 200:
        raise InvoiceServiceError(_error_detail(resp))
    body = resp.json()
    if not body.get('success'):
        raise InvoiceServiceError(body.get('message') or 'Сервис счетов не отправил файл')
