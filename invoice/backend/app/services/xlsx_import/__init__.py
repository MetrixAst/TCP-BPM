"""xlsx как альтернативный источник данных наравне с 1С — для ТЦ, у которых
1С нет/не актуальна, или которые сами говорят, что xlsx у них более свежий
(см. Tenant.xlsx_priority). Эталонная реализация построена на реальном
файле Maxi Mall.

Слои (каждый — независимо тестируемый, общий код не знает про конкретный ТЦ):

    upload (HTTP, следующий слой)
        -> TenantDataFile (аудит: кто/когда/что загрузил)
    parse (per-tenant, parsers/<tenant>.py)
        -> RawChargeRow — данные ровно как в файле, без единого решения
    normalize (общий, normalize.py)
        -> NormalizedRow — статус/матчинг контрагента/синтетические id уже
           приняты; тот же shape, что 1С-путь кладёт в TenantPayment
    upsert (общий, upsert.py)
        -> TenantPayment(source="xlsx") — тот же апсерт-контракт, что и
           sync_from_1c, поэтому вся дальнейшая логика (напоминания,
           реестр, аналитика) не знает, что источник — не 1С.

Верхнеуровневая точка входа — import_tenant_file() ниже."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.catalog import Tenant
from app.services.xlsx_import import balances as balances_module
from app.services.xlsx_import import normalize as normalize_module
from app.services.xlsx_import import phones as phones_module
from app.services.xlsx_import import upsert as upsert_module
from app.services.xlsx_import.registry import get_parser
from app.services.xlsx_import.types import ImportSummary


def import_tenant_file(db: Session, tenant: Tenant, file_bytes: bytes) -> ImportSummary:
    if not tenant.xlsx_parser_key:
        raise ValueError(f"Tenant {tenant.id} не настроен на xlsx-импорт (xlsx_parser_key пуст)")

    parser = get_parser(tenant.xlsx_parser_key)
    parse_result = parser(file_bytes)
    normalized = normalize_module.normalize(db, tenant, parse_result.rows)
    summary = upsert_module.apply(
        db,
        tenant.id,
        normalized,
        periods=parse_result.periods,
        totals_check=parse_result.totals_check,
        warnings=parse_result.warnings,
    )
    # Долг/Аванс/Нетто по контрагентам ("Статус платежей" в invoice-client) —
    # excel уже даёт остаток на строку, отдельный источник не нужен. По всем
    # tenant_payments(source="xlsx") арендатора, не только этой загрузки —
    # см. balances.py docstring.
    balances_module.recompute_xlsx_balances(db, tenant.id)
    # Контрагент из xlsx, что не сопоставился ни с одним реальным 1С-
    # контрагентом, иначе нигде не появляется, кроме tenant_payments —
    # вкладка «Контрагенты» ничего не покажет для xlsx-only арендатора без
    # этого. См. counterparty_cache_service.sync_xlsx_counterparty_directory.
    from app.services.counterparty_cache_service import sync_xlsx_counterparty_directory

    sync_xlsx_counterparty_directory(db, tenant.id, normalized)
    # Телефон получателя WhatsApp, если файл его несёт (см. parsers/
    # avantage.py) — только заполняет CounterpartyPhone, где ещё пусто, не
    # перезаписывает: см. phones.py docstring.
    phones_module.sync_xlsx_counterparty_phones(db, tenant, normalized)

    # Живой баг, найден на проде 2026-08-28: карточки аналитики (реестр
    # оплат) продолжали показывать старые числа ПОСЛЕ полной замены данных
    # выше — до 5 минут (_ANALYTICS_CACHE_TTL_SEC), сколько ни жми "Обновить
    # записи в реестре" на фронте. Причина — payment_sync_jobs.py (1С-путь)
    # всегда сбрасывал этот кэш после синка, а у xlsx-пути такого вызова
    # просто не было. tenant_id без period — сбрасывает все периоды/фильтры
    # этого арендатора разом, а не только периоды из этой конкретной
    # загрузки (полная замена выше могла задеть остатки и по другим
    # периодам через recompute_xlsx_balances).
    from app.services.counterparty_cache_service import invalidate_invoice_status_cache
    from app.services.payment_service import invalidate_analytics_cache

    invalidate_analytics_cache(tenant.id)
    invalidate_invoice_status_cache(tenant.id)
    return summary
