"""Обработка задач WhatsApp из очереди Kafka."""
from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from datetime import date as date_cls

from sqlalchemy import func

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.notification import Notification, NotificationStatus
from app.models.payment import TenantPayment
from app.services.auto_notification_service import astana_today
from app.services.counterparty_phone_routing import mark_counterparty_whatsapp_sent
from app.services.invoice_access import find_cached_invoice_pdf, get_trc_id_for_tenant
from app.services.safe_filename import safe_filename_component
from app.services.invoice_service_type import (
    due_date_in_invoice_month,
    due_day_for_service_type,
    format_service_types_label,
    resolve_invoice_service_types,
    tenant_due_day_for_service,
)
from app.services.message_builder import build_whatsapp_message
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id
from app.services.tenant_whatsapp import get_whatsapp_for_tenant

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Реальный инцидент на проде 2026-08-25: массовая рассылка должникам (180
# счетов) — Nova (onec.buh.getpdf, за её собственным openresty) отвечала
# 502 на КАЖДЫЙ запрос PDF ~15 минут подряд (два всплеска). Без ретрая здесь
# один короткий сбой на стороне Nova стоил счёта — job улетал в Kafka-реквью
# (см. kafka_worker.MAX_WHATSAPP_JOB_RETRIES), но там нет задержки между
# попытками, так что 3 мгновенных повтора просто утыкались в то же самое
# окно недоступности и не помогали.
_PDF_DOWNLOAD_RETRIES = 3
_PDF_DOWNLOAD_BACKOFF_SECONDS = 2.0  # 2s, 4s между попытками (после 1й — без паузы)


def _parse_invoice_date(raw) -> Optional[date_cls]:
    if not raw:
        return None
    text = str(raw).strip().split("T")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _refresh_placeholder_payment(
    db,
    *,
    tenant_id: Optional[int],
    payment_id: Optional[int],
    invoice_id: Optional[str],
    service_type: Optional[str],
) -> None:
    """/notifications/send создаёт для Nova-арендаторов заглушку TenantPayment
    (amount=None, invoice_date=due_date=сегодня, tenant_name=counterparty_name
    или, если 1С не вернул имя, сырой counterparty_id — см. app/api/notifications.py,
    ветка defer_pdf_to_worker), если строки для этого счёта ещё не было — просто
    чтобы было к чему привязать Notification. Реальные данные подтягиваются
    обычным синком, но до него сообщение уходит с "Сумма: 0 тг" и сегодняшней
    датой вместо настоящего срока, а в реестре — с GUID вместо имени и без типа
    счёта — правим всё это здесь, перед сборкой текста, одним live-запросом к
    1С (мы и так в фоне, не в request-пути — тут это не проблема, в отличие от
    /notifications/send)."""
    if not payment_id or not invoice_id:
        return
    payment = db.query(TenantPayment).filter(TenantPayment.id == payment_id).first()
    if not payment or payment.amount is not None:
        return  # не заглушка — уже есть реальная сумма (обычный синк дошёл)

    integration = get_integration_for_tenant(db, tenant_id)
    client = integration.client if integration else None
    fetch = getattr(client, "fetch_invoice_payment_status", None)
    if not callable(fetch):
        return
    try:
        inv = fetch(invoice_id)
    except Exception as exc:
        logger.warning(
            "Placeholder payment refresh failed invoice=%s: %s", invoice_id, exc
        )
        return
    finally:
        if hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass
    if not inv or not getattr(inv, "amount", None):
        return

    inv_date = _parse_invoice_date(getattr(inv, "date", None)) or payment.invoice_date
    tenant = get_tenant_by_id(db, tenant_id) if tenant_id else None
    due_day = due_day_for_service_type(
        service_type or "rent",
        rent=tenant_due_day_for_service(tenant, "rent"),
        utilities=tenant_due_day_for_service(tenant, "utilities"),
        operations=tenant_due_day_for_service(tenant, "operations"),
    )
    payment.amount = int(round(float(inv.amount)))
    payment.invoice_date = inv_date
    payment.due_date = due_date_in_invoice_month(inv_date, due_day)

    cp_key = (payment.counterparty_id or "").strip().lower()
    current_name = (payment.tenant_name or "").strip()
    if not current_name or current_name.lower() == cp_key:
        real_name = (getattr(inv, "counterparty_name", None) or "").strip()
        if real_name:
            payment.tenant_name = real_name
    if not (payment.service_type or "").strip():
        types = resolve_invoice_service_types(getattr(inv, "items", None) or [])
        payment.service_type = format_service_types_label(types)

    db.commit()


def _touch_counterparty_last_sent(
    db,
    *,
    tenant_id: Optional[int],
    payment_id: Optional[int] = None,
    counterparty_id: Optional[str] = None,
) -> None:
    """Обновить last_whatsapp_sent_at контрагента после успешной отправки.
    Не должно ронять доставку — любая ошибка здесь только логируется."""
    try:
        if not counterparty_id and payment_id:
            payment = db.query(TenantPayment).filter(TenantPayment.id == payment_id).first()
            counterparty_id = payment.counterparty_id if payment else None
        if not counterparty_id:
            return
        trc_id = get_trc_id_for_tenant(db, tenant_id)
        mark_counterparty_whatsapp_sent(db, trc_id=trc_id, counterparty_id=counterparty_id)
    except Exception:
        logger.exception(
            "Failed to update last_whatsapp_sent_at (tenant_id=%s payment_id=%s counterparty_id=%s)",
            tenant_id,
            payment_id,
            counterparty_id,
        )


def _outbox_dir() -> Path:
    custom = (os.getenv("WHATSAPP_OUTBOX_DIR") or "").strip()
    if custom:
        return Path(custom)
    return BACKEND_ROOT / "uploads" / "outbox"


def _pdf_matches_invoice(file_path: str, invoice_id: str) -> bool:
    """Real bug found 2026-09-02: files are saved via _resolve_downloads_path()
    (nova_buh_1c_client.py), which runs the invoice_id through
    safe_filename_component() first — replacing characters like ":" with "_"
    for filesystem safety. A real 1C GUID has none of those characters, so
    the raw invoice_id happened to already equal its sanitized form and this
    comparison worked by accident. An xlsx-sourced invoice_id
    ("xlsx:5:2026-08:cp:rent") does contain ":" — comparing it unsanitized
    against a sanitized filename always failed, silently discarding a
    correctly pre-rendered xlsx PDF on every Kafka-queued send (worker path)
    and falling through to a live 1C re-fetch that can never resolve a
    synthetic id. Sanitizing both sides the same way fixes this without
    changing behavior for real GUIDs at all (safe_filename_component is a
    no-op on hex+hyphen strings)."""
    inv_key = (invoice_id or "").strip().lower()
    if not inv_key:
        return True
    safe_inv_key = safe_filename_component(inv_key)
    name = Path(file_path).name.lower()
    return safe_inv_key in name or name == f"invoice_{safe_inv_key}.pdf"


def persist_outbox_file(source_path: str, suffix: str = ".pdf") -> str:
    outbox = _outbox_dir()
    outbox.mkdir(parents=True, exist_ok=True)
    src = Path(source_path)
    dest = outbox / f"{src.stem}_{src.stat().st_mtime_ns}{suffix}"
    shutil.copy2(src, dest)
    return str(dest.resolve())


def _materialize_job_file(payload: dict[str, Any]) -> Optional[str]:
    """Восстановить вложение на worker: локальный путь или base64 из Kafka."""
    file_path = payload.get("file_path")
    if file_path and Path(file_path).is_file():
        return str(Path(file_path).resolve())

    raw_b64 = payload.get("file_base64")
    if not raw_b64:
        return None
    try:
        data = base64.b64decode(str(raw_b64), validate=False)
    except (ValueError, TypeError) as exc:
        logger.warning("WhatsApp job: invalid file_base64: %s", exc)
        return None
    if len(data) < 500 or not data.startswith(b"%PDF"):
        logger.warning("WhatsApp job: file_base64 is not a valid PDF (%s bytes)", len(data))
        return None

    outbox = _outbox_dir()
    outbox.mkdir(parents=True, exist_ok=True)
    raw_name = str(payload.get("file_name") or "attachment.pdf").strip() or "attachment.pdf"
    safe_name = Path(raw_name).name.replace("/", "_")
    job_key = str(payload.get("job_id") or uuid.uuid4())
    dest = outbox / f"kafka_{job_key}_{safe_name}"
    try:
        dest.write_bytes(data)
    except OSError as exc:
        logger.warning("WhatsApp job: cannot write embedded PDF %s: %s", dest, exc)
        return None
    logger.info("WhatsApp job: materialized embedded PDF (%s bytes) -> %s", len(data), dest)
    return str(dest.resolve())


def _download_invoice_pdf(
    db,
    *,
    tenant_id: Optional[int],
    invoice_id: str,
) -> Optional[str]:
    """Живой запрос PDF в 1С с ретраями — сама сборка PDF в Nova/OData не
    ретраит транзитные 502/таймауты внутри себя (см. _PDF_DOWNLOAD_RETRIES
    выше), а один неудачный запрос без этого стоил счёта целиком."""
    integration = get_integration_for_tenant(db, tenant_id)
    tenant = get_tenant_by_id(db, tenant_id) if tenant_id else None
    try:
        if not integration.client:
            return None
        last_exc: Optional[Exception] = None
        for attempt in range(1, _PDF_DOWNLOAD_RETRIES + 1):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp_path = tmp.name
            try:
                result = integration.get_invoice_and_download(invoice_id, tenant=tenant)
                if result and Path(result).is_file():
                    return result
                Path(tmp_path).unlink(missing_ok=True)
            except Exception as exc:
                last_exc = exc
                Path(tmp_path).unlink(missing_ok=True)
                logger.warning(
                    "Worker PDF download attempt %s/%s failed invoice=%s: %s",
                    attempt,
                    _PDF_DOWNLOAD_RETRIES,
                    invoice_id,
                    exc,
                )
            if attempt < _PDF_DOWNLOAD_RETRIES:
                time.sleep(_PDF_DOWNLOAD_BACKOFF_SECONDS * attempt)
        if last_exc is None:
            logger.warning(
                "Worker PDF download: 1C returned no file after %s attempts, invoice=%s",
                _PDF_DOWNLOAD_RETRIES,
                invoice_id,
            )
        return None
    finally:
        if hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass


def _resolve_invoice_on_worker(
    db,
    *,
    tenant_id: Optional[int],
    counterparty_id: Optional[str],
    service_type: Optional[str],
    invoice_id: Optional[str],
) -> Optional[str]:
    if invoice_id:
        return invoice_id
    if not counterparty_id:
        return None
    from app.services.invoice_access import (
        find_invoice_id_for_service_type,
        find_latest_invoice_id,
    )

    integration = get_integration_for_tenant(db, tenant_id)
    tenant = get_tenant_by_id(db, tenant_id) if tenant_id else None
    try:
        if not integration.client:
            logger.warning(
                "Worker: 1C client unavailable for tenant %s (invoice resolve)",
                tenant_id,
            )
            return None
        st = (service_type or "").strip().lower()
        if st:
            return find_invoice_id_for_service_type(
                integration,
                counterparty_id,
                st,
                tenant=tenant,
            )
        return find_latest_invoice_id(integration, counterparty_id)
    except Exception as exc:
        logger.warning(
            "Worker invoice resolve failed tenant=%s cp=%s: %s",
            tenant_id,
            counterparty_id,
            exc,
        )
        return None
    finally:
        if hasattr(integration, "close"):
            try:
                integration.close()
            except Exception:
                pass


def _resolve_job_file_path(
    db,
    *,
    tenant_id: Optional[int],
    file_path: Optional[str],
    invoice_id: Optional[str],
    payment_id: Optional[int],
) -> Optional[str]:
    resolved_invoice = invoice_id
    if not resolved_invoice and payment_id:
        payment = db.query(TenantPayment).filter(TenantPayment.id == payment_id).first()
        if payment and payment.invoice_id:
            resolved_invoice = payment.invoice_id

    if file_path and Path(file_path).is_file():
        if resolved_invoice and not _pdf_matches_invoice(file_path, resolved_invoice):
            logger.warning(
                "Ignoring file_path %s — does not match invoice %s",
                file_path,
                resolved_invoice,
            )
            file_path = None
        else:
            return file_path
    elif file_path:
        logger.warning("WhatsApp job: file_path missing on worker: %s", file_path)

    if resolved_invoice:
        downloaded = _download_invoice_pdf(
            db,
            tenant_id=tenant_id,
            invoice_id=resolved_invoice,
        )
        if downloaded:
            return downloaded
        # Живой путь исчерпал ретраи (1С/Nova недоступна дольше, чем мы готовы
        # ждать один job) — тот же fallback на кэш, что уже есть у одиночной
        # отправки (app/api/notifications.py: find_cached_invoice_pdf). Раньше
        # его тут не было вообще: массовая рассылка не подхватывала PDF, даже
        # если он уже лежал на диске от предыдущей успешной отправки/синка
        # этого же счёта.
        cached = find_cached_invoice_pdf(resolved_invoice, db=db, tenant_id=tenant_id)
        if cached:
            logger.warning(
                "Worker PDF: используем кэш для %s — 1С недоступна для живой загрузки",
                resolved_invoice,
            )
            return cached
    return None


def _daily_send_count_for_tenant(db, tenant_id: Optional[int]) -> int:
    """Сколько WhatsApp-отправок этому арендатору уже ушло сегодня по нашей
    БД — fallback для _effective_daily_send_count, когда Green API
    lastOutgoingMessages недоступен (см. её докстринг). sent_at — UTC
    (server_default=func.now()), сравнение с датой по Astana (UTC+5)
    поэтому неточно в паре часов вокруг полуночи — не страшно для мягкого
    лимита такого масштаба (~200/сутки)."""
    if not tenant_id:
        return 0
    return (
        db.query(Notification)
        .join(TenantPayment, TenantPayment.id == Notification.payment_id)
        .filter(TenantPayment.tenant_id == tenant_id)
        .filter(func.date(Notification.sent_at) == astana_today())
        .count()
    )


def _effective_daily_send_count(db, tenant_id: Optional[int]) -> int:
    """Реальный дневной счётчик для settings.WHATSAPP_DAILY_SEND_CAP — по
    данным самого Green API (lastOutgoingMessages), а не только по нашей БД.

    Обнаружено 2026-09-10: аккаунт/номер может использоваться менеджером и
    вручную (не через наше приложение) — _daily_send_count_for_tenant видит
    только свои отправки и был бы слеп к ручному трафику, а WhatsApp/Green
    API банят по ОБЩЕМУ трафику номера (200/сутки — это не наш лимит, а
    лимит номера целиком). Живая проверка: 42 из 138 исходящих за 24ч на
    реальном инстансе были sendByApi=false (вручную).

    Если Green API недоступен — используем старый счётчик по своей БД
    (лучше недооценить лимит при сбое стороннего API, чем остановить
    рассылку целиком)."""
    real_count = get_whatsapp_for_tenant(db, tenant_id).get_today_outgoing_count()
    own_count = _daily_send_count_for_tenant(db, tenant_id)
    if real_count is None:
        logger.warning(
            "Green API lastOutgoingMessages недоступен (tenant_id=%s) — дневной "
            "лимит считается только по своей БД, может быть занижен",
            tenant_id,
        )
        return own_count
    return max(real_count, own_count)


def deliver_notification(
    db,
    notification_id: int,
    tenant_id: Optional[int],
    file_path: Optional[str],
    counterparty_name: Optional[str],
    service_type: Optional[str] = None,
    invoice_id: Optional[str] = None,
) -> bool:
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        logger.warning("WhatsApp job: notification %s not found", notification_id)
        return False

    try:
        _refresh_placeholder_payment(
            db,
            tenant_id=tenant_id,
            payment_id=notification.payment_id,
            invoice_id=invoice_id,
            service_type=service_type,
        )
        whatsapp = get_whatsapp_for_tenant(db, tenant_id)
        success = whatsapp.send_message(
            phone_number=notification.phone_number or "",
            message=build_whatsapp_message(
                db,
                tenant_id=tenant_id,
                payment_id=notification.payment_id,
                notification_type=notification.notification_type,
                counterparty_name=counterparty_name,
                service_type=service_type,
            ),
            file_path=file_path,
        )
        if success:
            # Раньше здесь сразу проставлялся DELIVERED — путало "Green API
            # принял наш HTTP-запрос" с "WhatsApp реально доставил
            # сообщение". Реальный инцидент 2026-09-09: 104 из 111 счетов
            # показывали "delivered" в нашей БД, хотя WhatsApp ничего не
            # доставил (инстанс словил временную блокировку сразу после
            # приёма запроса Green API — тот всё равно вернул 200). Статус
            # остаётся SENT (значение по умолчанию) до реального
            # подтверждения через outgoingMessageStatus вебхук — см.
            # _process_green_api_webhook ниже. green_api_id_message — ключ
            # для сопоставления с этим вебхуком, когда он придёт.
            notification.green_api_id_message = whatsapp.last_id_message
            _touch_counterparty_last_sent(db, tenant_id=tenant_id, payment_id=notification.payment_id)
        else:
            # Green API отказал (после ретраев на транспортном уровне в
            # whatsapp_service) — без этого статус оставался бы SENT навсегда,
            # неотличимо от "просто пока не подтверждено".
            notification.status = NotificationStatus.FAILED
            logger.error(
                "WhatsApp delivery failed (Green API): notification_id=%s tenant_id=%s phone=%s",
                notification_id,
                tenant_id,
                notification.phone_number,
            )
        db.commit()
        return bool(success)
    except Exception as exc:
        logger.exception("WhatsApp delivery failed notification_id=%s: %s", notification_id, exc)
        db.rollback()
        try:
            notification.status = NotificationStatus.FAILED
            db.commit()
        except Exception:
            db.rollback()
        return False


def deliver_raw_message(
    db,
    tenant_id: Optional[int],
    phone_number: str,
    message: str,
    file_path: Optional[str],
    counterparty_id: Optional[str] = None,
) -> bool:
    try:
        whatsapp = get_whatsapp_for_tenant(db, tenant_id)
        success = bool(
            whatsapp.send_message(
                phone_number=phone_number,
                message=message,
                file_path=file_path,
            )
        )
        if success:
            _touch_counterparty_last_sent(
                db, tenant_id=tenant_id, counterparty_id=counterparty_id
            )
        return success
    except Exception as exc:
        logger.exception("WhatsApp raw send failed: %s", exc)
        return False


def process_whatsapp_job(payload: dict[str, Any]) -> bool:
    """True — доставлено (или задача не подлежит повтору: неизвестный тип).
    False — не доставлено и стоит повторить (см. kafka_worker.py requeue с
    ограничением попыток по payload['_retry_count'])."""
    db = SessionLocal()
    try:
        kind = payload.get("type") or "whatsapp_send"
        if kind == "whatsapp_send":
            tenant_id_for_cap = payload.get("tenant_id")
            if tenant_id_for_cap and _effective_daily_send_count(db, tenant_id_for_cap) >= settings.WHATSAPP_DAILY_SEND_CAP:
                # Green API мягко рекомендует не более ~200 сообщений/сутки на
                # инстанс для массовых рассылок (иначе выглядит как
                # автоматизация — см. инцидент 2026-09-09). kafka_worker уже
                # ставит паузу между сообщениями (WHATSAPP_SEND_DELAY_SECONDS),
                # но за 8+ часов один день всё равно может превысить лимит —
                # это второй, дневной предохранитель. Возврат True (не
                # ретраить) — лимит не исчезнет от немедленного повтора в тот
                # же день; ставим FAILED, чтобы счёт не потерялся молча и
                # ушёл на ручной довоз/следующий день.
                logger.error(
                    "WhatsApp job dropped: daily send cap (%s) reached for tenant=%s "
                    "notification_id=%s — resend tomorrow or raise WHATSAPP_DAILY_SEND_CAP",
                    settings.WHATSAPP_DAILY_SEND_CAP,
                    tenant_id_for_cap,
                    payload.get("notification_id"),
                )
                notification = (
                    db.query(Notification)
                    .filter(Notification.id == payload.get("notification_id"))
                    .first()
                )
                if notification:
                    notification.status = NotificationStatus.FAILED
                    db.commit()
                return True
            invoice_id = _resolve_invoice_on_worker(
                db,
                tenant_id=payload.get("tenant_id"),
                counterparty_id=payload.get("counterparty_id"),
                service_type=payload.get("service_type"),
                invoice_id=payload.get("invoice_id"),
            )
            if not invoice_id:
                logger.error(
                    "WhatsApp job skipped: invoice not resolved (notification_id=%s)",
                    payload.get("notification_id"),
                )
                return False
            payment_id = payload.get("payment_id")
            if payment_id:
                payment = db.query(TenantPayment).filter(
                    TenantPayment.id == int(payment_id)
                ).first()
                if payment and not payment.invoice_id:
                    payment.invoice_id = invoice_id
                    db.commit()
            file_path = _resolve_job_file_path(
                db,
                tenant_id=payload.get("tenant_id"),
                file_path=payload.get("file_path"),
                invoice_id=invoice_id,
                payment_id=payment_id,
            )
            if not file_path:
                # Раньше это был return False — job улетал на Kafka-реквью
                # (kafka_worker.MAX_WHATSAPP_JOB_RETRIES=3, без задержки между
                # попытками), а при затяжном сбое источника PDF (реальный
                # инцидент 2026-08-25: Nova отдавала 502 на PDF ~15 минут
                # подряд на всю пачку должников) 3 мгновенных повтора просто
                # утыкались в то же окно недоступности — счёт терялся молча,
                # текст сообщения (сумма/срок/период — build_whatsapp_message)
                # никак не зависит от PDF, но не уходил тоже. Теперь после
                # ретраев+кэша (_resolve_job_file_path) шлём текстом без
                # вложения — должник хотя бы узнаёт о долге, а не остаётся
                # ни с чем из-за сбоя на стороне 1С.
                logger.warning(
                    "WhatsApp job: PDF not available after retries — sending text-only "
                    "(notification_id=%s invoice=%s)",
                    payload.get("notification_id"),
                    invoice_id,
                )
            return deliver_notification(
                db,
                notification_id=int(payload["notification_id"]),
                tenant_id=payload.get("tenant_id"),
                file_path=file_path,
                counterparty_name=payload.get("counterparty_name"),
                service_type=payload.get("service_type"),
                invoice_id=invoice_id,
            )
        elif kind == "whatsapp_file":
            file_path = _materialize_job_file(payload)
            if not file_path:
                file_path = _resolve_job_file_path(
                    db,
                    tenant_id=payload.get("tenant_id"),
                    file_path=payload.get("file_path"),
                    invoice_id=payload.get("invoice_id"),
                    payment_id=None,
                )
            if not file_path:
                logger.error(
                    "WhatsApp file job skipped: PDF not available (job_id=%s phone=%s)",
                    payload.get("job_id"),
                    payload.get("phone_number"),
                )
                return False
            return deliver_raw_message(
                db,
                tenant_id=payload.get("tenant_id"),
                phone_number=str(payload.get("phone_number") or ""),
                message=str(payload.get("message") or ""),
                file_path=file_path,
                counterparty_id=payload.get("counterparty_id"),
            )
        else:
            logger.warning("Unknown whatsapp job type: %s", kind)
            return True
    finally:
        db.close()


# outgoingMessageStatus.status -> NotificationStatus. "sent" не отображается —
# это и есть значение по умолчанию (см. deliver_notification), обновлять
# нечего. "suspended"/"noAccount"/"notInGroup"/"failed" — сообщение точно не
# дойдёт (реальный инцидент 2026-09-09: инстанс был как раз в "suspended" в
# момент отправки, хотя сам sendMessage вернул 200 и Notification выглядела
# успешной без этого вебхука).
_GREEN_API_DELIVERED_STATUSES = {"delivered", "read"}
_GREEN_API_FAILED_STATUSES = {"failed", "noAccount", "suspended", "notInGroup"}


def _process_green_api_webhook(db, body: dict[str, Any]) -> None:
    if (body or {}).get("typeWebhook") != "outgoingMessageStatus":
        return
    id_message = body.get("idMessage")
    wa_status = body.get("status")
    if not id_message or not wa_status:
        return

    notification = (
        db.query(Notification)
        .filter(Notification.green_api_id_message == id_message)
        .first()
    )
    if not notification:
        # Нормально для raw-отправок (deliver_raw_message — /send-file и т.п.)
        # без своей Notification-строки, а также для сообщений, отправленных
        # до 2026-09-10 (green_api_id_message ещё не заполнялся).
        return

    if wa_status in _GREEN_API_DELIVERED_STATUSES:
        from datetime import datetime

        notification.status = NotificationStatus.DELIVERED
        notification.delivered_at = datetime.utcnow()
        db.commit()
    elif wa_status in _GREEN_API_FAILED_STATUSES:
        logger.error(
            "WhatsApp delivery failed per Green API webhook: notification_id=%s "
            "status=%s (idMessage=%s)",
            notification.id, wa_status, id_message,
        )
        notification.status = NotificationStatus.FAILED
        db.commit()
    # остальные статусы ("sent" и любые новые/неизвестные) — не трогаем.


def process_webhook_job(payload: dict[str, Any]) -> None:
    source = payload.get("source", "unknown")
    if source == "green-api":
        db = SessionLocal()
        try:
            _process_green_api_webhook(db, payload.get("body") or {})
        except Exception:
            logger.exception(
                "Green API webhook processing failed job_id=%s", payload.get("job_id")
            )
            db.rollback()
        finally:
            db.close()
        return
    logger.info(
        "Webhook queued job source=%s job_id=%s (extend handler in whatsapp_jobs.process_webhook_job)",
        source,
        payload.get("job_id"),
    )
