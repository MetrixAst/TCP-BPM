"""Входящие вебхуки: только приём в Kafka, без синхронной обработки."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.job_queue import enqueue_webhook

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/green-api")
async def green_api_webhook(request: Request):
    try:
        body: Any = await request.json()
    except Exception:
        body = (await request.body()).decode("utf-8", errors="replace")

    headers = {k: v for k, v in request.headers.items() if k.lower().startswith("x-") or k.lower() == "authorization"}

    if settings.KAFKA_ENABLED:
        # Блокирующий KafkaProducer-вызов — без threadpool подвешивает
        # единственный uvicorn-воркер (см. аудит от 2026-08-25).
        ok = await run_in_threadpool(enqueue_webhook, "green-api", body, headers)
        if not ok:
            logger.error("Green API webhook: failed to enqueue")
            return {"accepted": False, "detail": "queue unavailable"}
        return {"accepted": True, "queued": True}

    logger.warning("Green API webhook received but KAFKA_ENABLED=false — enable Kafka for webhooks")
    return {"accepted": True, "queued": False, "detail": "process synchronously not implemented"}


@router.post("/{source}")
async def generic_webhook(source: str, request: Request):
    try:
        body: Any = await request.json()
    except Exception:
        body = (await request.body()).decode("utf-8", errors="replace")

    if settings.KAFKA_ENABLED:
        await run_in_threadpool(enqueue_webhook, source, body, None)
        return {"accepted": True, "queued": True}
    return {"accepted": True, "queued": False}
