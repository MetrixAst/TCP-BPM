import logging
from datetime import date, timedelta

from celery import shared_task
from django.core.cache import cache
from django.db.models import Q

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


@shared_task
def hr_check_expirations():
    """
    Ежедневная задача (06:00) — проверяет истечения документов, допусков и сертификаций.

    EmployeeDocument: active/expiring → expired (просрочен), active → expiring (за 30 дней).
    EmployeeWorkPermit: computed property — логируем истекающие/просроченные.
    EmployeeCertification: computed property — логируем истекающие/просроченные.
    """
    from hr.models import EmployeeDocument, EmployeeWorkPermit, EmployeeCertification
    from hr.enums import DocumentStatusEnum

    today = date.today()
    expiry_threshold = today + timedelta(days=30)

    # --- EmployeeDocument ---
    # active/expiring → expired
    expired_docs = EmployeeDocument.objects.filter(
        status__in=[DocumentStatusEnum.ACTIVE, DocumentStatusEnum.EXPIRING],
        expires_at__lt=today,
    )
    expired_docs_count = expired_docs.update(status=DocumentStatusEnum.EXPIRED)

    # active → expiring (expires within 30 days, not yet expired)
    expiring_docs = EmployeeDocument.objects.filter(
        status=DocumentStatusEnum.ACTIVE,
        expires_at__gte=today,
        expires_at__lte=expiry_threshold,
    )
    expiring_docs_count = expiring_docs.update(status=DocumentStatusEnum.EXPIRING)

    logger.info(
        f"hr_check_expirations: documents expired={expired_docs_count} expiring={expiring_docs_count}"
    )

    # --- EmployeeWorkPermit (computed status, log only) ---
    all_permits = EmployeeWorkPermit.objects.select_related('employee', 'category').all()
    permit_expiring = [p for p in all_permits if p.status == 'expiring']
    permit_expired = [p for p in all_permits if p.status == 'expired']

    logger.info(
        f"hr_check_expirations: work_permits expired={len(permit_expired)} expiring={len(permit_expiring)}"
    )

    # --- EmployeeCertification (computed status, log only) ---
    all_certs = EmployeeCertification.objects.select_related('employee', 'cert_type').filter(
        is_revoked=False,
        expiry_date__isnull=False,
    )
    cert_expiring = [c for c in all_certs if c.status == 'expiring']
    cert_expired = [c for c in all_certs if c.status == 'expired']

    logger.info(
        f"hr_check_expirations: certifications expired={len(cert_expired)} expiring={len(cert_expiring)}"
    )

    return {
        'documents': {'expired': expired_docs_count, 'expiring': expiring_docs_count},
        'work_permits': {'expired': len(permit_expired), 'expiring': len(permit_expiring)},
        'certifications': {'expired': len(cert_expired), 'expiring': len(cert_expiring)},
    }