"""Публикация фоновых задач в Kafka."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from app.core.config import settings
from app.services.kafka_client import kafka_connection_kwargs

logger = logging.getLogger(__name__)

_producer = None
_producer_lock = Lock()


def _producer_client():
    global _producer
    if _producer is not None:
        return _producer
    # Без лока конкурентные первые вызовы (threadpool-воркеры + APScheduler +
    # прямые вызовы из async-хендлеров) могли пройти проверку `is not None`
    # одновременно и создать по отдельному KafkaProducer каждый — лишнее
    # соединение/поток утекает молча (см. аудит от 2026-08-25).
    with _producer_lock:
        if _producer is not None:
            return _producer
        from kafka import KafkaProducer

        _producer = KafkaProducer(
            **kafka_connection_kwargs(),
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            acks="all",
            retries=3,
        )
        logger.info(
            "Kafka producer ready servers=%s protocol=%s",
            settings.KAFKA_BOOTSTRAP_SERVERS,
            settings.KAFKA_SECURITY_PROTOCOL,
        )
        return _producer


def publish(topic: str, payload: dict[str, Any], key: Optional[str] = None) -> bool:
    if not settings.KAFKA_ENABLED:
        return False
    message = {
        "job_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    try:
        producer = _producer_client()
        kafka_key = key.encode("utf-8") if key else None
        future = producer.send(topic, value=message, key=kafka_key)
        future.get(timeout=15)
        logger.info(
            "Kafka enqueue ok topic=%s job_id=%s type=%s",
            topic,
            message["job_id"],
            payload.get("type"),
        )
        return True
    except Exception as exc:
        logger.error("Kafka publish failed topic=%s: %s", topic, exc)
        return False


def enqueue_whatsapp_job(payload: dict[str, Any]) -> bool:
    return publish(
        settings.KAFKA_TOPIC_WHATSAPP,
        {"type": "whatsapp_send", **payload},
        key=str(payload.get("tenant_id") or payload.get("notification_id") or ""),
    )


def enqueue_webhook(source: str, body: Any, headers: Optional[dict[str, str]] = None) -> bool:
    return publish(
        settings.KAFKA_TOPIC_WEBHOOK,
        {
            "type": "webhook",
            "source": source,
            "body": body,
            "headers": headers or {},
        },
        key=source,
    )


def enqueue_payment_sync(
    *,
    tenant_id: Optional[int],
    period: str,
    sync_counterparties: bool = True,
) -> bool:
    return publish(
        settings.KAFKA_TOPIC_PAYMENTS_SYNC,
        {
            "type": "payment_sync",
            "tenant_id": tenant_id,
            "period": period,
            "sync_counterparties": sync_counterparties,
        },
        key=f"{tenant_id or 0}:{period}",
    )


def enqueue_counterparty_sync(*, tenant_id: int) -> bool:
    return publish(
        settings.KAFKA_TOPIC_PAYMENTS_SYNC,
        {
            "type": "counterparty_sync",
            "tenant_id": tenant_id,
        },
        key=f"cp:{tenant_id}",
    )
