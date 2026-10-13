import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def fetch_exchange_rates(date_str: str | None = None):
    """
    Ежедневная задача (14:00) — загружает курсы валют с НБ РК и сохраняет в БД.

    :param date_str: дата в формате 'YYYY-MM-DD' (опционально, для ручного запуска).
    """
    from datetime import date
    from finances.services.nbrk import fetch_nbrk_rates, save_nbrk_rates

    target_date = None
    if date_str:
        target_date = date.fromisoformat(date_str)

    try:
        rates = fetch_nbrk_rates(target_date)
        result = save_nbrk_rates(rates)
        logger.info(f"fetch_exchange_rates: {result}")
        return result
    except Exception as exc:
        logger.exception(f"fetch_exchange_rates_error: {exc}")
        raise


@shared_task(name='finances.sync_invoice_service')
def sync_invoice_service():
    """Загрузка счетов и оплат из invoice-сервиса (источник — 1С)."""
    from finances.services.invoice_service import is_configured
    from finances.services.invoice_sync import sync_invoices_from_service

    from finances.services.rent_plan import generate_rent_plan

    result = 'invoice-сервис не настроен'
    if is_configured():
        run = sync_invoices_from_service(trigger='schedule')
        result = f'{run.get_status_display()}: {run.stats}'
    plan = generate_rent_plan()
    return f'{result}; план по договорам: {plan}'
