import logging
import datetime

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="finances.tasks.fetch_exchange_rates",
    bind=True,
    max_retries=3,
    default_retry_delay=60 * 5,  
)
def fetch_exchange_rates(self, date_str: str | None = None):
    from finances.services.nbrk import fetch_and_save_rates, NBRKServiceError

    date: datetime.date | None = None
    if date_str:
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            logger.error("Некорректный формат даты: %s. Ожидается YYYY-MM-DD.", date_str)
            return {"status": "error", "detail": f"Некорректная дата: {date_str}"}

    target = date or datetime.date.today()
    logger.info("Загрузка курсов НБ РК за %s", target)

    try:
        created, updated = fetch_and_save_rates(date=date)
    except NBRKServiceError as exc:
        logger.error("Ошибка загрузки курсов НБ РК: %s", exc)
        raise self.retry(exc=exc)

    result = {
        "status": "ok",
        "date": str(target),
        "created": created,
        "updated": updated,
    }
    logger.info("Курсы НБ РК за %s: создано=%d, обновлено=%d", target, created, updated)
    return result