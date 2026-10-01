"""Проверка: счёт и PDF принадлежат конкретному контрагенту; WhatsApp — только на его телефон."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Optional, Set

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.catalog import CounterpartyPhone
from app.models.payment import TenantPayment
from app.services.invoice_service_type import (
    ServiceType,
    resolve_invoice_service_types,
    tenant_payment_keywords,
)
from app.services.integration_1c import Integration1C
from app.services.phone_list import normalize_phone, normalized_phone_set, split_phone_values
from app.services.safe_filename import safe_filename_component
from app.services.tenant_1c import get_tenant_by_id


def _raise_if_nova_unavailable(exc: Exception) -> None:
    from app.services.nova_1c_service import Nova1CServiceError

    if isinstance(exc, Nova1CServiceError):
        raise HTTPException(
            status_code=503,
            detail=(
                f"1С Nova недоступна: {exc}. "
                "Проверьте NOVA_ADMIN_EMAIL и NOVA_ADMIN_PASSWORD в Secret pod'а "
                "(пустые переменные не должны затирать .env образа)."
            ),
        ) from exc


def normalize_counterparty_id(counterparty_id: str) -> str:
    return (counterparty_id or "").strip().lower()


def _cached_pdf_meta_has_supplier_banks(pdf_path: Path) -> bool:
    meta_path = pdf_path.with_suffix(".pdf.meta.json")
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return bool(
        str(meta.get("supplier_iik") or "").strip()
        and str(meta.get("supplier_bik") or "").strip()
    )


def find_cached_invoice_pdf(
    invoice_id: str,
    *,
    db: Optional[Session] = None,
    tenant_id: Optional[int] = None,
) -> Optional[str]:
    """Кэшированный PDF счёта из downloads/.

    Раньше файл искался только по invoice_id — COM/Nova invoice_id не
    гарантированно глобально уникален между 1С-организациями, так что при
    совпадении один арендатор мог получить чужой кэшированный PDF (чужие
    банковские реквизиты/название контрагента, см. аудит от 2026-08-25). Когда
    вызывающий код передаёт db+tenant_id, дополнительно проверяем через
    tenant_payments.tenant_id (FK), что этот invoice_id вообще принадлежит
    запрошенному арендатору, прежде чем отдавать файл.
    """
    if not invoice_id:
        return None
    if db is not None and tenant_id:
        owned = (
            db.query(TenantPayment.id)
            .filter(
                func.lower(TenantPayment.invoice_id) == invoice_id.strip().lower(),
                TenantPayment.tenant_id == tenant_id,
            )
            .first()
        )
        if not owned:
            return None
    name = f"invoice_{safe_filename_component(invoice_id)}.pdf"
    cwd = Path(os.getcwd())
    candidates = [
        cwd / "downloads" / name,
        cwd / "backend" / "downloads" / name,
        Path(__file__).resolve().parent.parent.parent / "downloads" / name,
        Path(__file__).resolve().parent.parent / "downloads" / name,
    ]
    for path in candidates:
        if path.is_file() and _cached_pdf_meta_has_supplier_banks(path):
            return str(path.resolve())
    return None


def get_trc_id_for_tenant(db: Session, tenant_id: Optional[int]) -> Optional[int]:
    tenant = get_tenant_by_id(db, tenant_id)
    return tenant.trc_id if tenant else None


def get_invoice_counterparty_id(integration: Integration1C, invoice_id: str) -> Optional[str]:
    client = integration.client
    if not client:
        return None
    if hasattr(client, "get_invoice_counterparty_id"):
        return client.get_invoice_counterparty_id(invoice_id)
    invoices = client.get_invoices(limit=50000, enrich_payment_status=False)
    key = invoice_id.strip().lower()
    for inv in invoices:
        if (inv.id or "").strip().lower() == key:
            return inv.counterparty_id or None
    return None


def invoice_belongs_to_counterparty_in_db(
    db: Session,
    invoice_id: str,
    counterparty_id: str,
    *,
    tenant_id: Optional[int] = None,
) -> bool:
    """Проверка по tenant_payments после sync — без live 1С."""
    inv_key = (invoice_id or "").strip().lower()
    cp_key = normalize_counterparty_id(counterparty_id)
    if not inv_key or not cp_key:
        return False
    query = db.query(TenantPayment).filter(
        func.lower(TenantPayment.invoice_id) == inv_key,
        func.lower(TenantPayment.counterparty_id) == cp_key,
    )
    if tenant_id:
        # tenant_id (FK), не ip_name==legal_name — см. аудит от 2026-08-25.
        query = query.filter(TenantPayment.tenant_id == tenant_id)
    return query.first() is not None


def assert_invoice_belongs_to_counterparty(
    integration: Integration1C,
    invoice_id: str,
    counterparty_id: str,
) -> None:
    owner = get_invoice_counterparty_id(integration, invoice_id)
    if not owner:
        raise HTTPException(
            status_code=404,
            detail="Счёт не найден в 1С",
        )
    if normalize_counterparty_id(owner) != normalize_counterparty_id(counterparty_id):
        raise HTTPException(
            status_code=403,
            detail="Счёт не принадлежит указанному контрагенту",
        )


def _invoice_counterparty_id(inv) -> str:
    if isinstance(inv, dict):
        cp = inv.get("counterparty") or {}
        return str(inv.get("counterparty_id") or cp.get("id") or "")
    cp = getattr(inv, "counterparty", None)
    if isinstance(cp, dict):
        return str(getattr(inv, "counterparty_id", None) or cp.get("id") or "")
    return str(getattr(inv, "counterparty_id", None) or "")


def filter_invoices_by_counterparty(invoices: list, counterparty_id: str) -> list:
    cp_key = normalize_counterparty_id(counterparty_id)
    return [
        inv
        for inv in invoices
        if normalize_counterparty_id(_invoice_counterparty_id(inv)) == cp_key
    ]


def get_1c_phones_for_counterparty(
    integration: Integration1C,
    counterparty_id: str,
) -> Set[str]:
    """Телефоны из справочника контрагентов 1С (OData)."""
    client = integration.client
    if not client:
        return set()
    cp_key = normalize_counterparty_id(counterparty_id)
    phones: Set[str] = set()
    try:
        for cp in client.get_counterparties(limit=50000):
            if normalize_counterparty_id(cp.id or "") != cp_key:
                continue
            for raw in (cp.phone, cp.phone_number):
                for value in split_phone_values(raw):
                    normalized = normalize_phone(value)
                    if normalized:
                        phones.add(normalized)
            break
    except Exception:
        pass
    return phones


def collect_allowed_phones(
    db: Session,
    tenant_id: Optional[int],
    counterparty_id: str,
    integration: Optional[Integration1C] = None,
) -> Set[str]:
    """Телефоны из админки + из 1С для этого контрагента."""
    phones: Set[str] = set()
    trc_id = get_trc_id_for_tenant(db, tenant_id)
    if trc_id:
        phones |= get_allowed_phones(db, trc_id, counterparty_id)
    if integration:
        phones |= get_1c_phones_for_counterparty(integration, counterparty_id)
    return phones


def get_allowed_phones(
    db: Session,
    trc_id: int,
    counterparty_id: str,
) -> Set[str]:
    cp_key = normalize_counterparty_id(counterparty_id)
    rows = (
        db.query(CounterpartyPhone)
        .filter(CounterpartyPhone.trc_id == trc_id)
        .all()
    )
    phones: Set[str] = set()
    for row in rows:
        if normalize_counterparty_id(row.one_c_counterparty_id) == cp_key:
            phones |= normalized_phone_set(row.phone)
    return phones


def assert_phone_allowed_for_counterparty(
    db: Session,
    tenant_id: Optional[int],
    counterparty_id: str,
    phone_number: str,
    *,
    integration: Optional[Integration1C] = None,
) -> None:
    """
    Номер должен совпадать с телефоном контрагента из 1С или из админки.
    Если в 1С/админке телефонов нет — допускается номер из запроса (клик в таблице).
    """
    normalized = normalize_phone(phone_number)
    if not normalized:
        raise HTTPException(status_code=400, detail="Укажите номер телефона")

    allowed = collect_allowed_phones(db, tenant_id, counterparty_id, integration)
    if not allowed:
        return

    if normalized not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Номер не совпадает с телефоном этого контрагента в 1С",
        )


def invoice_service_types_from_1c(client, invoice, tenant=None) -> List[ServiceType]:
    """
    Тип услуг по строкам счёта из 1С (табличная часть /Услуги, /Товары).
    Список счетов OData не содержит строк — при наличии invoice_id всегда читаем live.
    """
    keywords = tenant_payment_keywords(tenant)
    invoice_id = (getattr(invoice, "id", None) or "").strip()
    if invoice_id and hasattr(client, "fetch_invoice_line_items"):
        types = resolve_invoice_service_types(
            client.fetch_invoice_line_items(invoice_id),
            keywords=keywords,
        )
        if types:
            return types
    return resolve_invoice_service_types(
        getattr(invoice, "items", None) or [],
        keywords=keywords,
    )


_invoice_service_types_from_client = invoice_service_types_from_1c


def find_invoice_id_for_service_type(
    integration: Integration1C,
    counterparty_id: str,
    service_type: str,
    *,
    since=None,
    tenant=None,
) -> Optional[str]:
    """Последний счёт контрагента с нужным типом услуг (по строкам 1С)."""
    client = integration.client
    if not client:
        return None
    cp_key = normalize_counterparty_id(counterparty_id)
    try:
        invoices = client.get_invoices(
            since=since, limit=50000, enrich_payment_status=False
        )
    except Exception as exc:
        _raise_if_nova_unavailable(exc)
        raise
    matching = [
        inv
        for inv in invoices
        if normalize_counterparty_id(inv.counterparty_id or "") == cp_key
    ]
    matching.sort(key=lambda x: x.date or "", reverse=True)
    for inv in matching:
        inv_id = (inv.id or "").strip()
        if not inv_id:
            continue
        types = invoice_service_types_from_1c(client, inv, tenant)
        if service_type in types:
            return inv_id
    return None


def find_latest_invoice_id(
    integration: Integration1C,
    counterparty_id: str,
    *,
    since=None,
) -> Optional[str]:
    client = integration.client
    if not client:
        return None
    try:
        invoices = client.get_invoices(
            since=since, limit=50000, enrich_payment_status=False
        )
    except Exception as exc:
        _raise_if_nova_unavailable(exc)
        raise
    cp_key = normalize_counterparty_id(counterparty_id)
    matching = [
        inv
        for inv in invoices
        if normalize_counterparty_id(inv.counterparty_id or "") == cp_key
    ]
    if not matching:
        return None
    matching.sort(key=lambda x: x.date or "", reverse=True)
    return matching[0].id


def resolve_invoice_for_counterparty(
    integration: Integration1C,
    invoice_id: Optional[str],
    counterparty_id: Optional[str],
    *,
    since=None,
    db: Optional[Session] = None,
    tenant_id: Optional[int] = None,
    skip_live_1c: bool = False,
) -> tuple[str, str]:
    """Возвращает (invoice_id, counterparty_id) с проверкой владельца."""
    if not counterparty_id and not invoice_id:
        raise HTTPException(
            status_code=400,
            detail="Укажите counterparty_id и/или invoice_id",
        )
    if invoice_id and counterparty_id:
        if skip_live_1c:
            if db and invoice_belongs_to_counterparty_in_db(
                db, invoice_id, counterparty_id, tenant_id=tenant_id
            ):
                return invoice_id, counterparty_id
            return invoice_id, counterparty_id
        assert_invoice_belongs_to_counterparty(
            integration, invoice_id, counterparty_id
        )
        return invoice_id, counterparty_id
    if counterparty_id and not invoice_id:
        latest = find_latest_invoice_id(integration, counterparty_id, since=since)
        if not latest:
            raise HTTPException(
                status_code=404,
                detail="Для контрагента не найдено счетов в 1С",
            )
        return latest, counterparty_id
    owner = get_invoice_counterparty_id(integration, invoice_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Счёт не найден в 1С")
    return invoice_id, owner
