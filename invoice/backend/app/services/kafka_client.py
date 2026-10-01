"""Общие настройки подключения к Kafka"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def kafka_bootstrap_servers() -> list[str]:
    return [s.strip() for s in settings.KAFKA_BOOTSTRAP_SERVERS.split(",") if s.strip()]


def kafka_connection_kwargs() -> dict:
    """
    Аргументы для kafka-python KafkaProducer / KafkaConsumer.
    Локально: PLAINTEXT + localhost:9092.
    Кластер: SASL_PLAINTEXT + kafka-cluster-kafka-bootstrap...:9092.
    """
    kwargs: dict = {"bootstrap_servers": kafka_bootstrap_servers()}
    protocol = (settings.KAFKA_SECURITY_PROTOCOL or "PLAINTEXT").strip().upper()
    if protocol == "PLAINTEXT":
        return kwargs

    kwargs["security_protocol"] = protocol
    mechanism = (settings.KAFKA_SASL_MECHANISM or "PLAIN").strip()
    kwargs["sasl_mechanism"] = mechanism

    username = (settings.KAFKA_SASL_USERNAME or "").strip()
    password = settings.KAFKA_SASL_PASSWORD or ""
    if not username:
        logger.warning(
            "Kafka %s without KAFKA_SASL_USERNAME — connection may fail",
            protocol,
        )
    else:
        kwargs["sasl_plain_username"] = username
        kwargs["sasl_plain_password"] = password

    return kwargs
