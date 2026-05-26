import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _format_sync_result(result: dict, *, ok_template: str, err_label: str = 'Сбой синхронизации') -> str:
    if result.get('status') == 'skipped':
        return f"{err_label}: {result.get('reason', 'skipped')}"
    if result.get('status') == 'error':
        return f"{err_label}: {result.get('error', 'unknown')}"
    if result.get('status') == 'ok':
        return ok_template.format(**result)
    return str(result)


@shared_task(name='sync_counterparties_task')
def sync_counterparties():
    from onec.services.sync_counterparties import sync_counterparties_from_1c

    result = sync_counterparties_from_1c()
    if result.get('status') == 'ok' and result.get('message') == 'no_data':
        return 'No data received'
    return _format_sync_result(
        result,
        ok_template='Синхронизация завершена: создано {created}, обновлено {updated}',
    )


@shared_task(name='sync_onec_cashflow_task')
def sync_onec_cashflow():
    from onec.services.sync_cashflow import sync_cashflow_from_1c
    return sync_cashflow_from_1c()


@shared_task(name='sync_onec_registry_task')
def sync_onec_registry():
    from onec.services.sync_registry import sync_registry_from_1c
    return sync_registry_from_1c()


@shared_task(name='sync_onec_invoices_task')
def sync_onec_invoices():
    from onec.services.sync_invoices import sync_generated_invoices_from_1c
    return sync_generated_invoices_from_1c()


@shared_task(name='sync_onec_data_queue_task')
def sync_onec_data_queue():
    from onec.services.sync_data_queue import sync_data_queue_from_1c
    return sync_data_queue_from_1c()


@shared_task(name='sync_onec_all_task')
def sync_onec_all():
    from onec.services.sync_all import sync_all_from_1c
    return sync_all_from_1c()
