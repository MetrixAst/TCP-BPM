"""Очередь PULL /data → finances + confirm."""

from __future__ import annotations

import logging

from .client_factory import get_onec_client, is_onec_configured
from .sync_cashflow import upsert_payment
from .sync_financial import _apply_budget_fact_payload, _apply_opiu_payload

logger = logging.getLogger(__name__)


def sync_data_queue_from_1c(*, financial_only: bool = False) -> dict:
    if not is_onec_configured():
        return {'status': 'skipped', 'reason': 'onec_not_configured'}

    client = get_onec_client()
    confirmed = opiu = budget = payments = ignored = 0
    received_ids = []

    try:
        response = client.get_data(limit=500)
    except Exception as exc:
        logger.exception('sync_data_queue: %s', exc)
        return {'status': 'error', 'error': str(exc)}

    for record in response.data:
        payload = record.data if isinstance(record.data, dict) else {}
        rtype = (record.type or '').lower()
        received_ids.append(record.id)

        if financial_only and rtype not in (
            'financial_statement', 'opiu', 'pnl', 'budget_fact', 'budget',
        ):
            continue

        if rtype in ('financial_statement', 'opiu', 'pnl', 'profit_loss', 'statement'):
            if _apply_opiu_payload(payload, onec_id=record.id):
                opiu += 1
        elif rtype in ('budget_fact', 'budget', 'budget_item'):
            if _apply_budget_fact_payload(payload):
                budget += 1
        elif rtype in ('payment', 'cashflow', 'dds') and not financial_only:
            upsert_payment(payload, onec_id=record.id)
            payments += 1
        else:
            ignored += 1

    if received_ids and response.sync_token:
        try:
            client.confirm(received_ids=received_ids, sync_token=response.sync_token)
            confirmed = len(received_ids)
        except Exception as exc:
            logger.warning('confirm failed: %s', exc)

    return {
        'status': 'ok',
        'confirmed': confirmed,
        'opiu': opiu,
        'budget': budget,
        'payments': payments,
        'ignored': ignored,
    }
