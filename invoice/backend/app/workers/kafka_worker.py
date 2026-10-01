"""
Consumer Kafka: WhatsApp и входящие вебхуки.
Запуск: python -m app.workers.kafka_worker
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
from typing import Optional

from kafka import KafkaConsumer

from app.core.config import settings
from app.services.kafka_client import kafka_connection_kwargs
from app.services.payment_sync_jobs import process_payment_sync_job
from app.services.whatsapp_jobs import process_webhook_job, process_whatsapp_job

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# app/main.py делает sentry_sdk.init() — но этот воркер отдельный процесс
# (python -m app.workers.kafka_worker), который app.main никогда не импортирует,
# так что без этого падения/сбои отправки WhatsApp были невидимы для Sentry,
# хотя это ровно то место, где реально уходит Green API запрос.
# Guard по "pytest" — тот же, что в app/main.py: иначе тестовый прогон,
# который просто импортирует этот модуль (см. tests/test_whatsapp_resilience.py),
# реально шлёт события в Sentry-проект.
if settings.SENTRY_DSN and "pytest" not in sys.modules:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.1,
    )

# Сколько раз повторно поставить в очередь job WhatsApp-отправки, если она не
# доехала. Сама отправка в whatsapp_service.py уже ретраит на HTTP-уровне
# (429/5xx/сеть, с backoff 1/2/4 сек) — это следующий уровень, без задержки
# между попытками (Kafka не умеет delay-очереди), поэтому от долгого сбоя
# Green API (минуты) не спасает — для этого есть NotificationStatus.FAILED +
# Sentry-алерт, чтобы не потерять счёт молча и переотправить вручную позже.
# Здесь цель — не устроить retry-storm на постоянно битой задаче (невалидный
# телефон и т.п.), а не бесконечно ждать восстановления провайдера.
MAX_WHATSAPP_JOB_RETRIES = 3
# Раньше только whatsapp-задачи ретраились при ошибке — payment_sync/webhook
# при исключении просто логировались и терялись без единой попытки
# восстановления (см. аудит от 2026-08-25, "payment sync jobs never retried").
MAX_JOB_RETRIES = 3

_shutdown_requested = False


def _handle_shutdown_signal(signum, _frame) -> None:
    # Не выходим немедленно: даём текущему poll()/сообщению доиграть, чтобы не
    # обработать половину job'а и не закоммитить офсет раньше времени —
    # SIGTERM прилетает на каждый rolling deploy/рестарт пода, а раньше здесь
    # не было вообще никакого обработчика (см. аудит от 2026-08-25).
    global _shutdown_requested
    logger.info("Received signal %s — finishing current message, then shutting down", signum)
    _shutdown_requested = True


def _requeue_whatsapp_job(payload: dict) -> None:
    from app.services.job_queue import enqueue_whatsapp_job

    retry_count = int(payload.get("_retry_count") or 0)
    if retry_count >= MAX_WHATSAPP_JOB_RETRIES:
        logger.error(
            "WhatsApp job giving up after %s retries: notification_id=%s job_id=%s",
            retry_count,
            payload.get("notification_id"),
            payload.get("job_id"),
        )
        return
    payload = {**payload, "_retry_count": retry_count + 1}
    if not enqueue_whatsapp_job(payload):
        logger.error(
            "WhatsApp job requeue failed (Kafka publish error): notification_id=%s",
            payload.get("notification_id"),
        )


def _requeue_job_via_publish(topic: str, payload: dict, key: Optional[bytes]) -> None:
    """Generic requeue for topics with no dedicated enqueue_* wrapper that
    would preserve arbitrary payload fields. enqueue_payment_sync/enqueue_webhook
    each build their own fixed payload shape from named kwargs — routing a
    retry through them would silently drop _retry_count and reset the cap
    (effectively an infinite retry loop on a permanently-broken job), so this
    republishes the exact payload via job_queue.publish() directly instead.
    """
    from app.services.job_queue import publish

    retry_count = int(payload.get("_retry_count") or 0)
    if retry_count >= MAX_JOB_RETRIES:
        logger.error(
            "Job giving up after %s retries topic=%s job_id=%s",
            retry_count,
            topic,
            payload.get("job_id"),
        )
        return
    new_payload = {**payload, "_retry_count": retry_count + 1}
    key_str = key.decode("utf-8") if isinstance(key, (bytes, bytearray)) else key
    if not publish(topic, new_payload, key=key_str):
        logger.error(
            "Job requeue failed (Kafka publish error) topic=%s job_id=%s",
            topic,
            payload.get("job_id"),
        )


def _paced_sleep(seconds: float) -> None:
    """Спим кусками по 1 сек, проверяя _shutdown_requested — иначе долгая
    пауза (WHATSAPP_SEND_DELAY_SECONDS, по умолчанию 45с) заметно задерживает
    graceful shutdown на SIGTERM (см. _handle_shutdown_signal)."""
    remaining = seconds
    while remaining > 0 and not _shutdown_requested:
        time.sleep(min(1.0, remaining))
        remaining -= 1.0


def _process_message(consumer: KafkaConsumer, message) -> None:
    payload = message.value or {}
    topic = message.topic
    try:
        if topic == settings.KAFKA_TOPIC_WHATSAPP:
            ok = process_whatsapp_job(payload)
            if not ok:
                _requeue_whatsapp_job(payload)
        elif topic == settings.KAFKA_TOPIC_WEBHOOK:
            process_webhook_job(payload)
        elif topic == settings.KAFKA_TOPIC_PAYMENTS_SYNC:
            process_payment_sync_job(payload)
    except Exception as exc:
        logger.exception(
            "Job failed topic=%s job_id=%s: %s",
            topic,
            payload.get("job_id"),
            exc,
        )
        if topic == settings.KAFKA_TOPIC_WHATSAPP:
            _requeue_whatsapp_job(payload)
        else:
            _requeue_job_via_publish(topic, payload, message.key)
    finally:
        # enable_auto_commit=False (см. main()) — коммитим офсет только здесь,
        # после того как с сообщением сделано всё, что мы собирались (обработано
        # успешно, или неуспех уже переотправлен в очередь как новая задача).
        # Раньше офсет коммитился автоматически по таймеру независимо от того,
        # успела ли обработка завершиться — убийство процесса (OOM, рестарт
        # пода, деплой) между авто-коммитом и концом обработки молча теряло
        # сообщение навсегда, и это происходило бы при каждом обычном деплое
        # (см. аудит от 2026-08-25).
        try:
            consumer.commit()
        except Exception:
            logger.exception(
                "Failed to commit offset topic=%s partition=%s offset=%s — "
                "message will be reprocessed after restart",
                message.topic,
                message.partition,
                message.offset,
            )
        if topic == settings.KAFKA_TOPIC_WHATSAPP:
            # Пауза регистрируется независимо от исхода (success/failure/
            # exception) — это ограничение исходящего трафика на инстанс
            # Green API, а не per-job логика. Реальный инцидент 2026-09-09:
            # 111 WhatsApp-отправок ушли из этого воркера за одну минуту
            # (max_records=10 на poll(), без паузы между сообщениями вообще)
            # — инстанс словил временную блокировку от WhatsApp, 104 из 111
            # счетов не дошли. Второй уровень защиты (первый — Green API
            # SetSettings.delaySendMessagesMilliseconds, см.
            # whatsapp_service.set_send_delay) на случай прямой отправки в
            # обход воркера. После commit(), а не до — коммит офсета не
            # должен ждать паузу отправки.
            _paced_sleep(settings.WHATSAPP_SEND_DELAY_SECONDS)


def main() -> None:
    if not settings.KAFKA_ENABLED:
        logger.error("KAFKA_ENABLED=false — worker не запускается")
        sys.exit(1)

    topics = [
        settings.KAFKA_TOPIC_WHATSAPP,
        settings.KAFKA_TOPIC_WEBHOOK,
        settings.KAFKA_TOPIC_PAYMENTS_SYNC,
    ]
    consumer = KafkaConsumer(
        *topics,
        **kafka_connection_kwargs(),
        group_id=settings.KAFKA_CONSUMER_GROUP,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    logger.info(
        "Kafka worker started topics=%s group=%s servers=%s protocol=%s",
        topics,
        settings.KAFKA_CONSUMER_GROUP,
        settings.KAFKA_BOOTSTRAP_SERVERS,
        settings.KAFKA_SECURITY_PROTOCOL,
    )

    try:
        # Ручной poll() вместо `for message in consumer:` — блокирующий
        # итератор не даёт шанса проверить _shutdown_requested между
        # сообщениями, только между отдельными poll()-вызовами.
        while not _shutdown_requested:
            batches = consumer.poll(timeout_ms=1000, max_records=10)
            for records in batches.values():
                for message in records:
                    _process_message(consumer, message)
                    if _shutdown_requested:
                        break
    finally:
        logger.info("Kafka worker shutting down, closing consumer")
        consumer.close()


if __name__ == "__main__":
    main()
