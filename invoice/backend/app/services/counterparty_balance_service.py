"""Синк и чтение BUH balance (debit/credit/net) — без изменения логики счетов."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.counterparty_balance import CounterpartyBalance
from app.models.counterparty_cache import CounterpartyCache
from app.services.counterparty_name_match import (
    build_name_resolution_index,
    resolve_to_cache_counterparty_id,
    virtual_counterparty_key,
)
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id

logger = logging.getLogger(__name__)

# копейки считаем нулём — иначе net «пляшет»
_ZERO_EPS = Decimal("1")


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _cp_key(raw: Any) -> str:
    return str(raw or "").strip().lower()


def net_of(debit: Decimal, credit: Decimal) -> Decimal:
    return debit - credit


def balance_label(debit: Decimal, credit: Decimal) -> str:
    """Короткий ярлык для UI: долг / аванс / ноль."""
    d = debit if abs(debit) >= _ZERO_EPS else Decimal("0")
    c = credit if abs(credit) >= _ZERO_EPS else Decimal("0")
    n = d - c
    if n > 0:
        return "debt"
    if c > 0:
        return "advance"
    return "zero"


def balances_map_for_tenant(db: Session, tenant_id: int) -> dict[str, dict[str, Any]]:
    """counterparty_id → {debit, credit, net, label, name, synced_at}."""
    rows = (
        db.query(CounterpartyBalance)
        .filter(CounterpartyBalance.tenant_id == tenant_id)
        .all()
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _cp_key(row.counterparty_id)
        if not key:
            continue
        debit = _to_decimal(row.debit)
        credit = _to_decimal(row.credit)
        out[key] = {
            "debit": float(debit),
            "credit": float(credit),
            "net": float(net_of(debit, credit)),
            "label": balance_label(debit, credit),
            "counterpartyName": row.counterparty_name or "",
            "syncedAt": row.synced_at.isoformat() if row.synced_at else None,
        }
    return out


_AGING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("aging_current", "current"),
    ("aging_30", "days30"),
    ("aging_60", "days60"),
    ("aging_90", "days90"),
    ("aging_over120", "over120"),
    ("aging_unknown", "unknown"),
    ("aging_total", "total"),
)


def _zero_aging() -> dict[str, float]:
    return {key: 0.0 for _, key in _AGING_COLUMNS}


def trc_debt_summary(db: Session, trc_id: int) -> dict[str, Any]:
    """
    Сводка долга по всем арендаторам ТРЦ — для карточки в админке.
    Долг/аванс считаем как net (debit-credit), а не сырой debit — аванс
    (net<0) не должен попадать в «должен нам». Аренда с odata_direct без
    fetch_balance_by_counterparty (см. OData1CClient) не имеет строк в
    CounterpartyBalance вообще — явно помечаем has_balance_data=False, а не
    молча показываем ноль (ноль неотличим от «реально нет долга»).
    """
    from app.models.catalog import Tenant

    tenants = (
        db.query(Tenant)
        .filter(Tenant.trc_id == trc_id, Tenant.is_active.is_(True))
        .order_by(Tenant.id)
        .all()
    )

    total_debt = Decimal("0")
    total_advance = Decimal("0")
    total_aging = {key: Decimal("0") for _, key in _AGING_COLUMNS}
    tenants_with_data = 0
    tenants_without_data = 0
    by_tenant: list[dict[str, Any]] = []

    for tenant in tenants:
        rows = (
            db.query(CounterpartyBalance)
            .filter(CounterpartyBalance.tenant_id == tenant.id)
            .all()
        )
        if not rows:
            tenants_without_data += 1
            by_tenant.append(
                {
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "has_balance_data": False,
                    "synced_at": None,
                    "debt": 0.0,
                    "advance": 0.0,
                    "aging": _zero_aging(),
                }
            )
            continue

        tenants_with_data += 1
        t_debt = Decimal("0")
        t_advance = Decimal("0")
        t_aging = {key: Decimal("0") for _, key in _AGING_COLUMNS}
        latest_sync = None
        for row in rows:
            net = net_of(_to_decimal(row.debit), _to_decimal(row.credit))
            if net > _ZERO_EPS:
                t_debt += net
                # aging — только для реальных должников, иначе бакеты по
                # авансовым/нулевым строкам задвоят total относительно debt.
                for col, key in _AGING_COLUMNS:
                    val = getattr(row, col, None)
                    if val is not None:
                        t_aging[key] += _to_decimal(val)
            elif net < -_ZERO_EPS:
                t_advance += -net
            if row.synced_at and (latest_sync is None or row.synced_at > latest_sync):
                latest_sync = row.synced_at

        total_debt += t_debt
        total_advance += t_advance
        for _, key in _AGING_COLUMNS:
            total_aging[key] += t_aging[key]
        by_tenant.append(
            {
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "has_balance_data": True,
                "synced_at": latest_sync,
                "debt": float(t_debt),
                "advance": float(t_advance),
                "aging": {key: float(val) for key, val in t_aging.items()},
            }
        )

    by_tenant.sort(key=lambda item: item["debt"], reverse=True)
    return {
        "trc_id": trc_id,
        "total_debt": float(total_debt),
        "total_advance": float(total_advance),
        "aging": {key: float(val) for key, val in total_aging.items()},
        "tenants_with_data": tenants_with_data,
        "tenants_without_data": tenants_without_data,
        "by_tenant": by_tenant,
    }


def tenant_has_balance_snapshot(db: Session, tenant_id: int) -> bool:
    return (
        db.query(CounterpartyBalance.tenant_id)
        .filter(CounterpartyBalance.tenant_id == tenant_id)
        .limit(1)
        .first()
        is not None
    )


def is_real_debtor_net(net: float | Decimal | None) -> bool:
    """Реальный долг по взаиморасчётам — net > 0."""
    try:
        return Decimal(str(net or 0)) > _ZERO_EPS
    except (InvalidOperation, ValueError, TypeError):
        return False


def replace_balances_for_tenant(
    db: Session,
    tenant_id: int,
    rows: list[dict[str, Any]],
) -> int:
    """Полная замена снимка по арендатору (как пришло из balance).

    xlsx-строки (source="xlsx", см. xlsx_import/balances.py) исключены из
    удаления/перезаписи — иначе этот полный replace на каждом часовом 1С-синке
    тихо стирал бы то, что посчитано из excel-файла, без какого-либо сигнала
    (см. аудит от 2026-08-26). "Sticky" до следующей xlsx-загрузки того же
    контрагента — независимо от текущего Tenant.xlsx_priority."""
    now = datetime.now(timezone.utc)
    xlsx_cp_ids = {
        row[0]
        for row in db.query(CounterpartyBalance.counterparty_id)
        .filter(
            CounterpartyBalance.tenant_id == tenant_id,
            CounterpartyBalance.source == "xlsx",
        )
        .all()
    }
    delete_query = db.query(CounterpartyBalance).filter(CounterpartyBalance.tenant_id == tenant_id)
    if xlsx_cp_ids:
        delete_query = delete_query.filter(~CounterpartyBalance.counterparty_id.in_(xlsx_cp_ids))
    delete_query.delete(synchronize_session=False)

    aging_keys = (
        "aging_current",
        "aging_30",
        "aging_60",
        "aging_90",
        "aging_over120",
        "aging_unknown",
        "aging_total",
    )

    # Несколько строк на одного контрагента — норма (COM без Ref схлопывает
    # по имени, либо 1С отдаёт по документам/договорам): суммируем, PK один на tenant+cp_id.
    merged: dict[str, dict[str, Any]] = {}
    for item in rows:
        cp_id = _cp_key(item.get("counterparty_id") or item.get("id"))
        if not cp_id:
            continue
        debit = _to_decimal(item.get("debit"))
        credit = _to_decimal(item.get("credit"))
        name = (item.get("counterparty_name") or item.get("name") or "")[:512] or None
        if cp_id in merged:
            merged[cp_id]["debit"] += debit
            merged[cp_id]["credit"] += credit
            merged[cp_id]["name"] = merged[cp_id]["name"] or name
        else:
            merged[cp_id] = {"debit": debit, "credit": credit, "name": name}
        # aging — уже агрегировано по контрагенту в самой секции 1С (не по строкам
        # by_counterparty), поэтому берём один раз ("первое непустое"), не суммируем —
        # иначе задвоится при нескольких сырых строках на одного контрагента.
        for key in aging_keys:
            if merged[cp_id].get(key) is None and item.get(key) is not None:
                merged[cp_id][key] = _to_decimal(item.get(key))

    saved = 0
    for cp_id, agg in merged.items():
        if cp_id in xlsx_cp_ids:
            # excel уже владеет этой строкой (PK всё ещё существует, см. delete
            # выше) — вставка сюда была бы дублирующим PK, а не апдейтом.
            continue
        # пустые нули тоже пишем — иначе «нет строки» ≠ «ноль»
        db.add(
            CounterpartyBalance(
                tenant_id=tenant_id,
                counterparty_id=cp_id,
                counterparty_name=agg["name"],
                debit=agg["debit"],
                credit=agg["credit"],
                source="one_c",
                synced_at=now,
                **{key: agg.get(key) for key in aging_keys},
            )
        )
        saved += 1
    db.commit()
    return saved


def _resolve_missing_counterparty_ids(
    db: Session,
    tenant_id: int,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    COM buh.balance иногда отдаёт by_counterparty без Ref/id — только имя
    (см. Maxi Mall, org 119). Пытаемся найти настоящий id контрагента по имени
    в уже засинканном counterparty_cache; если не вышло — стабильный virtual:
    ключ (тот же приём, что и для счетов без UUID, см. counterparty_name_match).
    """
    if not any(not (row.get("counterparty_id") or "").strip() for row in rows):
        return rows

    cache_row = (
        db.query(CounterpartyCache)
        .filter(CounterpartyCache.tenant_id == tenant_id)
        .first()
    )
    name_index = build_name_resolution_index(cache_row.data or []) if cache_row and cache_row.data else {}

    resolved: list[dict[str, Any]] = []
    for row in rows:
        cp_id = (row.get("counterparty_id") or "").strip()
        if not cp_id:
            name = row.get("counterparty_name")
            cp_id = resolve_to_cache_counterparty_id(name, name_index) or virtual_counterparty_key(name or "")
            row = {**row, "counterparty_id": cp_id}
        resolved.append(row)
    return resolved


def sync_counterparty_balances(db: Session, tenant_id: int) -> dict[str, Any]:
    """
    Тянем onec.buh.balance и кладём by_counterparty в БД.
    Ошибки наружу — вызывающий ловит, счета/реестр не откатываем.
    """
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return {"ok": False, "saved": 0, "error": "tenant not found"}

    integration = get_integration_for_tenant(db, tenant_id)
    client = integration.client
    if not client:
        return {
            "ok": False,
            "saved": 0,
            "error": integration.unavailable_message() or "1C unavailable",
        }

    if not hasattr(client, "fetch_balance_by_counterparty"):
        return {
            "ok": False,
            "saved": 0,
            "error": "balance script not supported for this client",
        }

    if not getattr(client, "access_token", None):
        try:
            client.authenticate()
        except Exception as exc:
            return {"ok": False, "saved": 0, "error": str(exc)}

    rows = client.fetch_balance_by_counterparty() or []
    rows = _resolve_missing_counterparty_ids(db, tenant_id, rows)
    saved = replace_balances_for_tenant(db, tenant_id, rows)
    logger.info(
        "Balance snapshot synced tenant_id=%s rows=%s",
        tenant_id,
        saved,
    )
    return {"ok": True, "saved": saved, "error": None}


def sync_counterparty_balances_safe(tenant_id: int) -> None:
    """Обёртка для джоб: падение balance не валит sync счетов."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        result = sync_counterparty_balances(db, tenant_id)
        if not result.get("ok"):
            logger.warning(
                "Balance sync skipped/failed tenant_id=%s: %s",
                tenant_id,
                result.get("error"),
            )
    except Exception:
        logger.exception("Balance sync failed tenant_id=%s", tenant_id)
    finally:
        db.close()
