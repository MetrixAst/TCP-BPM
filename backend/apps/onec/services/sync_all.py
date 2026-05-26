"""Полная синхронизация 1С → BPM."""

from __future__ import annotations

import logging

from django.conf import settings

from .client_factory import is_onec_configured
from .sync_cashflow import sync_cashflow_from_1c
from .sync_data_queue import sync_data_queue_from_1c
from .sync_invoices import sync_generated_invoices_from_1c
from .sync_registry import sync_registry_from_1c

logger = logging.getLogger(__name__)


def sync_all_from_1c() -> dict:
    if not is_onec_configured():
        return {'status': 'skipped', 'reason': 'onec_not_configured'}

    if not getattr(settings, 'ONE_C_SYNC_ENABLED', True):
        return {'status': 'skipped', 'reason': 'ONE_C_SYNC_ENABLED=false'}

    results = {}

    from .sync_counterparties import sync_counterparties_from_1c
    results['counterparties'] = sync_counterparties_from_1c()

    results['cashflow'] = sync_cashflow_from_1c()
    results['registry'] = sync_registry_from_1c()
    results['invoices'] = sync_generated_invoices_from_1c()
    results['data_queue'] = sync_data_queue_from_1c()

    return {'status': 'ok', 'results': results}
