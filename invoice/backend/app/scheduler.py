from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.db.database import SessionLocal, engine
from app.services.pg_advisory_lock import try_advisory_lock
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

# Произвольные, но фиксированные ключи для pg_advisory_lock — уникальные в
# рамках этого приложения (общее int8-пространство на уровне кластера БД).
# Без них, при масштабировании API за пределы одной реплики, каждая реплика
# независимо шлёт одни и те же WhatsApp-напоминания и гоняет дублирующий
# sync 1С каждый час (см. аудит от 2026-08-25) — единственный сегодня
# instance получает лок мгновенно и без изменений в поведении.
_LOCK_KEY_AUTO_NOTIFICATIONS = 84_201_001
_LOCK_KEY_TENANT_DATA_SYNC = 84_201_002


def run_auto_invoice_notifications():
    with try_advisory_lock(engine, _LOCK_KEY_AUTO_NOTIFICATIONS) as acquired:
        if not acquired:
            logger.info(
                "Auto invoice notification job already running on another "
                "instance/overlap — skipping this tick"
            )
            return
        db = SessionLocal()
        try:
            from app.services.auto_notification_service import AutoNotificationService

            count = AutoNotificationService(db).run_for_all_tenants()
            logger.info("Auto invoice notification cycle done, sent=%s", count)
        except Exception as e:
            logger.error("Error in auto invoice notification job: %s", e)
        finally:
            db.close()


def run_hourly_tenant_data_sync():
    with try_advisory_lock(engine, _LOCK_KEY_TENANT_DATA_SYNC) as acquired:
        if not acquired:
            logger.info(
                "Hourly tenant data sync already running on another "
                "instance/overlap — skipping this tick"
            )
            return
        try:
            from app.services.counterparty_cache_service import schedule_all_active_tenants_sync

            count = schedule_all_active_tenants_sync()
            if count:
                logger.info("Hourly tenant data sync scheduled for %s tenants", count)
        except Exception as e:
            logger.error("Hourly tenant data sync failed: %s", e)


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        run_auto_invoice_notifications,
        trigger=IntervalTrigger(hours=1),
        id="auto_invoice_notifications",
        name="Auto invoice check every 1h; WhatsApp -5/-3/0/+1/+3/+5 days vs due, 09:00-18:00 Astana",
        replace_existing=True,
    )
    
    scheduler.add_job(
        run_hourly_tenant_data_sync,
        trigger=IntervalTrigger(minutes=60),
        id="hourly_tenant_data_sync",
        name="Hourly 1C sync to PostgreSQL (payments + counterparties)",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Notification scheduler started")


def shutdown_scheduler():
    if not scheduler.running:
        return
    scheduler.shutdown(wait=False)
    logger.info("Notification scheduler stopped")
