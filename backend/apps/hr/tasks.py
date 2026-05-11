import logging

from celery import shared_task
from django.core.cache import cache

from hr.services import EnbekSyncService

logger = logging.getLogger(__name__)


LOCK_KEY = "enbek_sync_lock"
LOCK_TIMEOUT = 60 * 60  


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def sync_enbek_data(self):
    logger.info("celery_sync_started")

    if cache.get(LOCK_KEY):
        logger.warning("sync_skipped_due_to_lock")
        return {"status": "skipped"}

    cache.set(LOCK_KEY, True, LOCK_TIMEOUT)

    try:
        service = EnbekSyncService()
        result = service.sync_all()

        logger.info(
            f"celery_sync_completed: created={result.get('created', 0)}, updated={result.get('updated', 0)}"
        )

        return result

    except Exception as e:
        logger.exception("celery_sync_error")
        raise e

    finally:
        cache.delete(LOCK_KEY)