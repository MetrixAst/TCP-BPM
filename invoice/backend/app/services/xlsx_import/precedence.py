"""Когда Tenant.xlsx_priority == "prefer_xlsx", 1С-синк продолжает работать
в фоне как есть (продуктовое решение от 2026-08-26: excel побеждает на
показе, 1С остаётся живым бэкапом/сверкой — синк НЕ глушим). Значит для
одного и того же реального начисления (тот же tenant/period/counterparty/
service_type) в tenant_payments могут одновременно жить и 1С-строка, и
xlsx-строка — они физически не сталкиваются по invoice_id (разные схемы:
GUID/номер из 1С против "xlsx:..." — см. upsert.py), апсерт их не сольёт.

Без подавления это значит: реестр показывает "два одинаковых счёта" на
одну аренду, аналитика их дважды считает, а рассылка должникам может
отправить два WhatsApp за один и тот же долг. exclude_shadowed_one_c_rows
режет 1С-строку, если для той же тройки (period, counterparty_id,
service_type) есть xlsx-строка — только для tenant'ов в prefer_xlsx,
остальных не трогает вообще."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Query, Session, aliased

from app.models.catalog import Tenant
from app.models.payment import TenantPayment


def exclude_shadowed_one_c_rows(db: Session, query: Query, tenant_id: Optional[int]) -> Query:
    """Применять СРАЗУ ПОСЛЕ фильтра по tenant_id — до этого cross-tenant
    korrelированный подзапрос ниже был бы бессмысленным/дорогим."""
    if not tenant_id:
        return query

    tenant_row = db.query(Tenant.xlsx_priority).filter(Tenant.id == tenant_id).first()
    if not tenant_row or tenant_row[0] != "prefer_xlsx":
        return query

    Shadow = aliased(TenantPayment)
    shadow_exists = (
        db.query(Shadow.id)
        .filter(
            Shadow.tenant_id == tenant_id,
            Shadow.source == "xlsx",
            Shadow.period == TenantPayment.period,
            Shadow.counterparty_id == TenantPayment.counterparty_id,
            Shadow.service_type == TenantPayment.service_type,
        )
        .exists()
    )
    return query.filter(~and_(TenantPayment.source == "one_c", shadow_exists))
