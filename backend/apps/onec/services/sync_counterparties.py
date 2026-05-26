"""Синхронизация контрагентов из 1С."""

from __future__ import annotations

import logging

from django.utils import timezone

from onec.models import Counterparty

from .client_factory import get_onec_client, is_onec_configured

logger = logging.getLogger(__name__)


def _counterparty_defaults(item) -> dict | None:
    if isinstance(item, dict):
        id_1c = item.get('id_1c') or item.get('id')
        get_val = item.get
    else:
        id_1c = getattr(item, 'id_1c', None) or getattr(item, 'id', None)
        get_val = lambda k, default=None: getattr(item, k, default)

    if not id_1c:
        return None

    return {
        'id_1c': str(id_1c),
        'full_name': get_val('full_name', get_val('fullName', '')) or '',
        'short_name': get_val('short_name', get_val('shortName', '')) or '',
        'bin_number': get_val('bin_number', get_val('bin')),
        'iin': get_val('iin'),
        'address': get_val('address'),
        'phone': get_val('phone', get_val('phone_number')),
        'email': get_val('email'),
        'is_supplier': get_val('is_supplier', get_val('isSupplier', False)),
        'is_customer': get_val('is_customer', get_val('isCustomer', False)),
        'bank_accounts': get_val('bank_accounts', get_val('bankAccounts', [])) or [],
        'contracts': get_val('contracts', []) or [],
        'synced_at': timezone.now(),
    }


def sync_counterparties_from_1c() -> dict:
    if not is_onec_configured():
        return {'status': 'skipped', 'reason': 'onec_not_configured'}

    logger.info('Начало синхронизации контрагентов.')
    client = get_onec_client()
    created = updated = 0

    try:
        data = client.get_counterparties()
    except Exception as exc:
        logger.exception('sync_counterparties: %s', exc)
        return {'status': 'error', 'error': str(exc)}

    if not data:
        return {'status': 'ok', 'created': 0, 'updated': 0, 'message': 'no_data'}

    for item in data:
        defaults = _counterparty_defaults(item)
        if not defaults:
            continue
        id_1c = defaults.pop('id_1c')
        _, was_created = Counterparty.objects.update_or_create(
            id_1c=id_1c,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {'status': 'ok', 'created': created, 'updated': updated}
