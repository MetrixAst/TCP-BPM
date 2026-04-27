import logging
from django.utils import timezone
from django.conf import settings
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="sync_counterparties_task")
def sync_counterparties():
    from .models import Counterparty
    from .client_1c.client import Client1C

    logger.info("Начало синхронизации контрагентов.")

    client_1c = Client1C(
        base_url=settings.ONE_C_BASE_URL,
        basic_auth_user=settings.ONE_C_BASIC_AUTH_USER,
        basic_auth_password=settings.ONE_C_BASIC_AUTH_PASSWORD,
        api_user=settings.ONE_C_API_USER,
        api_password=settings.ONE_C_API_PASSWORD,
    )

    try:
        data = client_1c.get_counterparties()

        if not data:
            logger.warning("Данные от 1С не получены.")
            return "No data received"

        updated_count = 0
        created_count = 0

        for item in data:
            if isinstance(item, dict):
                id_1c = item.get("id_1c")
                def get_val(key, default=None):
                    return item.get(key, default)
            else:
                id_1c = getattr(item, "id_1c", None)
                def get_val(key, default=None):
                    return getattr(item, key, default)

            if not id_1c:
                logger.debug("Пропущена запись без id_1c: %s", item)
                continue

            obj, created = Counterparty.objects.update_or_create(
                id_1c=id_1c,
                defaults={
                    "full_name":     get_val("full_name", ""),
                    "short_name":    get_val("short_name", ""),
                    "bin_number":    get_val("bin_number"),
                    "iin":           get_val("iin"),
                    "address":       get_val("address"),
                    "phone":         get_val("phone"),
                    "email":         get_val("email"),
                    "is_supplier":   get_val("is_supplier", False),
                    "is_customer":   get_val("is_customer", False),
                    "bank_accounts": get_val("bank_accounts", []),
                    "contracts":     get_val("contracts", []),
                    "synced_at":     timezone.now(),
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        result_msg = (
            f"Синхронизация завершена: создано {created_count}, обновлено {updated_count}"
        )
        logger.info(result_msg)
        return result_msg

    except Exception as e:
        error_msg = f"Сбой синхронизации: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg