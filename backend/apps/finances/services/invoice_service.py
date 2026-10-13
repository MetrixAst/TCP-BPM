"""
Клиент invoice-сервиса Metrix (invoice.metrix.com.ai).

Сервис сам забирает счета и оплаты из 1С арендодателя (OData / Nova), хранит
реестр, формирует PDF и рассылает счета арендаторам через WhatsApp и e-mail.
BPM подключается к нему учётной записью уровня ТРЦ: такой токен видит только
организации своего ТРЦ.

Настройки (.env):
    INVOICE_SERVICE_URL       — https://api.invoice.metrix.com.ai
    INVOICE_SERVICE_USERNAME  — логин портала ТРЦ
    INVOICE_SERVICE_PASSWORD  — пароль портала ТРЦ
    INVOICE_SERVICE_TENANT_IDS — id организаций-арендодателей через запятую;
                                 пусто — единственная организация ТРЦ
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = 'invoice_service:token'
TOKEN_TTL = 60 * 60 * 20  # токен сервиса живёт 24 ч — обновляем заранее


class InvoiceServiceError(Exception):
    pass


class InvoiceServiceNotConfigured(InvoiceServiceError):
    pass


def is_configured() -> bool:
    return bool(
        getattr(settings, 'INVOICE_SERVICE_URL', '')
        and getattr(settings, 'INVOICE_SERVICE_USERNAME', '')
        and getattr(settings, 'INVOICE_SERVICE_PASSWORD', '')
    )


def configured_tenant_ids() -> list[int | None]:
    raw = getattr(settings, 'INVOICE_SERVICE_TENANT_IDS', '') or ''
    ids = [int(part) for part in raw.replace(' ', '').split(',') if part.isdigit()]
    return ids or [None]


class InvoiceServiceClient:
    def __init__(self, base_url=None, username=None, password=None, timeout=None, session=None):
        if not (base_url or is_configured()):
            raise InvoiceServiceNotConfigured(
                'Задайте INVOICE_SERVICE_URL, INVOICE_SERVICE_USERNAME и INVOICE_SERVICE_PASSWORD в .env'
            )
        self.base_url = (base_url or settings.INVOICE_SERVICE_URL).rstrip('/')
        self.username = username or settings.INVOICE_SERVICE_USERNAME
        self.password = password or settings.INVOICE_SERVICE_PASSWORD
        self.timeout = timeout or getattr(settings, 'INVOICE_SERVICE_TIMEOUT', 60)
        self.session = session or requests.Session()

    # ── авторизация ─────────────────────────────────────────────────────

    def _login(self) -> str:
        response = self.session.post(
            f'{self.base_url}/api/tenant-auth/login',
            json={'username': self.username, 'password': self.password},
            timeout=self.timeout,
        )
        if response.status_code == 401:
            raise InvoiceServiceError('Invoice-сервис: неверный логин или пароль ТРЦ')
        self._raise_for_status(response)
        token = response.json().get('access_token')
        if not token:
            raise InvoiceServiceError('Invoice-сервис не вернул токен')
        cache.set(TOKEN_CACHE_KEY, token, TOKEN_TTL)
        return token

    def _token(self, refresh=False) -> str:
        token = None if refresh else cache.get(TOKEN_CACHE_KEY)
        return token or self._login()

    def _request(self, method, path, *, params=None, json=None, stream=False):
        url = f'{self.base_url}{path}'
        params = {k: v for k, v in (params or {}).items() if v not in (None, '')}
        for attempt in (1, 2):
            headers = {'Authorization': f'Bearer {self._token(refresh=attempt == 2)}'}
            response = self.session.request(
                method, url, params=params, json=json, headers=headers,
                timeout=self.timeout, stream=stream,
            )
            if response.status_code != 401:
                break
        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response):
        if response.status_code < 400:
            return
        try:
            detail = response.json().get('detail')
        except ValueError:
            detail = response.text[:200]
        raise InvoiceServiceError(f'Invoice-сервис ответил {response.status_code}: {detail}')

    # ── чтение ──────────────────────────────────────────────────────────

    def list_invoices(self, period: str, *, tenant_id=None) -> list[dict]:
        """Счета периода YYYY-MM с позициями (из базы сервиса, без похода в 1С)."""
        data = self._request('GET', '/api/payments/1c/invoices', params={
            'period': period, 'tenant_id': tenant_id, 'source': 'db', 'limit': 50000,
        }).json()
        if data.get('error'):
            raise InvoiceServiceError(data['error'])
        return data.get('invoices') or []

    def list_payments(self, period: str, *, tenant_id=None) -> list[dict]:
        """Статусы оплат по счетам периода: сумма, оплачено, срок, дата оплаты."""
        items, page = [], 1
        while True:
            data = self._request('GET', '/api/payments', params={
                'period': period, 'tenant_id': tenant_id, 'page': page, 'page_size': 1000,
            }).json()
            items.extend(data.get('items') or [])
            if page >= (data.get('total_pages') or 1):
                return items
            page += 1

    def download_invoice_pdf(self, invoice_id: str, counterparty_id: str, *, tenant_id=None) -> bytes:
        response = self._request(
            'GET', f'/api/payments/1c/invoices/{invoice_id}/download',
            params={'counterparty_id': counterparty_id, 'tenant_id': tenant_id},
        )
        if 'pdf' not in response.headers.get('Content-Type', ''):
            raise InvoiceServiceError('Invoice-сервис не вернул PDF счёта')
        return response.content

    def start_sync(self, period: str, *, tenant_id=None) -> dict:
        """Попросить сервис обновить счета периода из 1С."""
        return self._request('POST', '/api/payments/sync', params={
            'period': period, 'tenant_id': tenant_id,
        }).json()

    # ── отправка ────────────────────────────────────────────────────────

    def send_whatsapp(self, *, phone: str, invoice_id: str, counterparty_id: str,
                      counterparty_name: str = '', payment_id=None, tenant_id=None) -> dict:
        return self._request(
            'POST', '/api/notifications/send',
            params={
                'tenant_id': tenant_id, 'invoice_id': invoice_id,
                'counterparty_id': counterparty_id, 'counterparty_name': counterparty_name,
            },
            json={
                'payment_id': payment_id,
                'notification_type': 'same_day',
                'phone_number': phone,
                'counterparty_id': counterparty_id,
                'invoice_id': invoice_id,
            },
        ).json()

    def send_email(self, *, invoice_id: str, counterparty_id: str, email: str = '',
                   counterparty_name: str = '', tenant_id=None) -> dict:
        data = self._request(
            'POST', '/api/notifications/send-email',
            params={'tenant_id': tenant_id},
            json={
                'counterparty_id': counterparty_id, 'invoice_id': invoice_id,
                'email': email or None, 'counterparty_name': counterparty_name or None,
            },
        ).json()
        if not data.get('ok'):
            raise InvoiceServiceError(data.get('message') or 'Письмо не отправлено')
        return data
