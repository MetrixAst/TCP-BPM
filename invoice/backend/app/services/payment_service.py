import logging
import time
from threading import Lock

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, case
from datetime import date, datetime
from typing import Optional, List

from fastapi import HTTPException
from app.models.payment import TenantPayment, PaymentStatus
from app.schemas.payment import PaymentFilter, PaymentAnalytics
from app.services.tenant_1c import get_integration_for_tenant, get_tenant_by_id, tenant_uses_nova_org
from app.services.integration_1c import Integration1C
from app.services.invoice_access import normalize_counterparty_id, resolve_invoice_for_counterparty
from app.services.payment_status_rules import payment_coverage_status
from app.services.xlsx_import.precedence import exclude_shadowed_one_c_rows
from app.services.invoice_service_type import (
    format_service_types_label,
    resolve_invoice_service_types,
)
from datetime import date, datetime, timedelta
from app.models.payment import PaymentStatus
from datetime import datetime
from app.models.notification import Notification, NotificationType, NotificationStatus

logger = logging.getLogger(__name__)

_ANALYTICS_CACHE: dict[str, tuple[float, PaymentAnalytics]] = {}
_ANALYTICS_CACHE_LOCK = Lock()
_ANALYTICS_CACHE_TTL_SEC = 300

_PAYMENT_TYPE_LABELS = {
    "rent": "Аренда",
    "utilities": "Коммунальные услуги",
    "operations": "Эксплуатация и маркетинг",
    "signage": "Вывеска",
    "assp": "АССП",
    "debt": "Долг пред. периода",
    "other": "Прочее",
    "unknown": "—",
}


def _analytics_cache_key(
    tenant_id: Optional[int],
    period: Optional[str],
    tenant_name: Optional[str],
    ip_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    service_type: Optional[str] = None,
) -> str:
    # ip_name обязателен в ключе: без tenant_id (админ-вид "по ИП без арендатора")
    # scope-фильтр всё равно режет по filters.ip_name (см. _apply_payment_filters),
    # а раньше ключ его не учитывал — один ИП мог получить карточки другого
    # (см. аудит от 2026-08-25). service_type добавлен тем же принципом —
    # _analytics_scope_filters теперь тоже его пропускает.
    df = date_from.isoformat() if date_from else ""
    dt = date_to.isoformat() if date_to else ""
    return (
        f"{tenant_id or 0}:{period or ''}:{df}:{dt}:{tenant_name or ''}:"
        f"{ip_name or ''}:{service_type or ''}"
    )


def invalidate_analytics_cache(
    tenant_id: Optional[int] = None,
    period: Optional[str] = None,
) -> None:
    """Сброс кэша карточек аналитики после sync или смены данных."""
    prefix = f"{tenant_id or 0}:"
    with _ANALYTICS_CACHE_LOCK:
        if tenant_id is None and period is None:
            _ANALYTICS_CACHE.clear()
            return
        keys = list(_ANALYTICS_CACHE.keys())
        for key in keys:
            if tenant_id is not None and not key.startswith(prefix):
                continue
            if period is not None and f":{period}:" not in f":{key}:":
                continue
            _ANALYTICS_CACHE.pop(key, None)


class PaymentService:
    def __init__(self, db: Session, tenant_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.integration_1c = get_integration_for_tenant(db, tenant_id)
    
    def is_test_mode(self, filters: PaymentFilter, status_param: Optional[str] = None) -> bool:

        status_is_test = status_param and str(status_param).lower() == "test"
        return (
            (filters.ip_name and filters.ip_name.lower() == "тест") or
            (filters.tenant_name and filters.tenant_name.lower() == "тест") or
            status_is_test
        )

    def calculate_status(self, due_date: date, paid_at: Optional[datetime]) -> PaymentStatus:

        if paid_at is not None:
            return PaymentStatus.PAID
        
        today = date.today()
        if today > due_date:
            return PaymentStatus.OVERDUE
        
        return PaymentStatus.UNPAID

    def _tenant_due_day(self) -> int:
        tenant = get_tenant_by_id(self.db, self.tenant_id) if self.tenant_id else None
        raw = getattr(tenant, "invoice_due_day", None)
        if raw is None:
            return 5
        try:
            return max(1, min(31, int(raw)))
        except (TypeError, ValueError):
            return 5

    def _invoice_in_period(self, invoice_date_str: str, period: str) -> bool:
        if not period or not invoice_date_str:
            return True
        raw = str(invoice_date_str).strip().split("T")[0]
        return raw.startswith(period)

    def _tenant_utilities_due_day(self) -> int:
        tenant = get_tenant_by_id(self.db, self.tenant_id) if self.tenant_id else None
        raw = getattr(tenant, "invoice_due_day_utilities", None) if tenant else None
        if raw is None:
            return self._tenant_due_day()
        try:
            return max(1, min(31, int(raw)))
        except (TypeError, ValueError):
            return self._tenant_due_day()

    def _tenant_operations_due_day(self) -> int:
        tenant = get_tenant_by_id(self.db, self.tenant_id) if self.tenant_id else None
        raw = getattr(tenant, "invoice_due_day_operations", None) if tenant else None
        if raw is None:
            return self._tenant_due_day()
        try:
            return max(1, min(31, int(raw)))
        except (TypeError, ValueError):
            return self._tenant_due_day()

    def get_analytics_from_1c(self, period: Optional[str]) -> Optional[PaymentAnalytics]:
        """Сводка по контрагентам из 1С (как в таблице контрагентов на вкладке реестра)."""
        client = self.integration_1c.client
        if not client or not hasattr(client, "get_latest_invoice_status_by_counterparty"):
            return None
        try:
            status_by_cp = client.get_latest_invoice_status_by_counterparty(
                due_day=self._tenant_due_day(),
                utilities_due_day=self._tenant_utilities_due_day(),
                operations_due_day=self._tenant_operations_due_day(),
                period=period,
            )
        except Exception as exc:
            logger.warning("1C analytics failed: %s", exc)
            return None

        paid = unpaid = overdue = 0
        for info in status_by_cp.values():
            status = str(info.get("paymentStatus") or "unpaid").lower()
            if status == "paid":
                paid += 1
            elif status == "overdue":
                overdue += 1
            else:
                unpaid += 1
        total = paid + unpaid + overdue
        if total == 0:
            return None
        return self._build_payment_analytics(
            total=total,
            paid=paid,
            unpaid=unpaid,
            overdue=overdue,
            source="1c_counterparties",
        )

    def _scope_query_by_tenant(self, query):
        """Ограничивает запрос текущим self.tenant_id по tenant_id (FK на
        tenants.id), а не по ip_name == tenant.legal_name.

        legal_name — свободный текст без уникальности на уровне БД: два
        арендатора с одинаковым/похожим именем (в одном ТЦ или в разных) могли
        видеть счета/платежи друг друга через эту старую логику (см. аудит от
        2026-08-25). tenant_id проставляется в sync_from_1c/
        ensure_payment_for_counterparty и был backfill'нут для исторических
        строк миграцией b0c1d2e3f4a5 — везде, где раньше сравнивали ip_name,
        теперь сравниваем настоящий внешний ключ.
        """
        if self.tenant_id:
            query = query.filter(TenantPayment.tenant_id == self.tenant_id)
            # prefer_xlsx: 1С-синк продолжает идти в фоне (продуктовое
            # решение — не глушим), но excel должен побеждать на показе —
            # см. xlsx_import/precedence.py docstring про дублирующиеся
            # счета/двойные напоминания без этого фильтра.
            query = exclude_shadowed_one_c_rows(self.db, query, self.tenant_id)
        return query

    def _apply_payment_filters(self, query, filters: PaymentFilter):
        """Фильтры реестра. tenant_name из каталога ≠ имени контрагента в БД."""
        if self.tenant_id:
            query = self._scope_query_by_tenant(query)
        else:
            if filters.ip_name and filters.ip_name != "Все":
                query = query.filter(TenantPayment.ip_name == filters.ip_name)
            if filters.tenant_name and filters.tenant_name != "Все":
                query = query.filter(TenantPayment.tenant_name == filters.tenant_name)

        if filters.date_from:
            query = query.filter(TenantPayment.invoice_date >= filters.date_from)
        if filters.date_to:
            query = query.filter(TenantPayment.invoice_date <= filters.date_to)
        if filters.period and not filters.date_from and not filters.date_to:
            query = query.filter(TenantPayment.period == filters.period)

        if filters.status:
            query = query.filter(TenantPayment.status == filters.status)
        if filters.service_type:
            # substring — "rent,utilities" должен находиться по фильтру "rent"
            query = query.filter(TenantPayment.service_type.ilike(f"%{filters.service_type}%"))
        return query

    def _payment_row_count(self, query, status: Optional[PaymentStatus] = None) -> int:
        q = query
        if status is not None:
            q = q.filter(TenantPayment.status == status)
        return int(q.count() or 0)

    def _status_from_sync_item(self, item: dict) -> PaymentStatus:
        """Статус из 1С (СтатусОплаты → payment_status). Без пересчёта overdue поверх unpaid."""
        raw = str(item.get("payment_status") or "").lower().strip()
        if raw in ("paid", "оплачен", "оплачено"):
            return PaymentStatus.PAID
        if raw in ("partial", "частично", "частично оплачен", "частично оплачено"):
            return PaymentStatus.PARTIAL
        if raw in ("overdue", "просрочен", "просрочено"):
            return PaymentStatus.OVERDUE
        if raw in ("unpaid", "не оплачен", "не оплачено", "неоплачен", "неоплачено"):
            return PaymentStatus.UNPAID
        return self.calculate_status(item["due_date"], item.get("paid_at"))

    def _analytics_cache_get(self, cache_key: str) -> Optional[PaymentAnalytics]:
        with _ANALYTICS_CACHE_LOCK:
            entry = _ANALYTICS_CACHE.get(cache_key)
            if not entry:
                return None
            ts, analytics = entry
            if time.time() - ts > _ANALYTICS_CACHE_TTL_SEC:
                _ANALYTICS_CACHE.pop(cache_key, None)
                return None
            return analytics

    def _analytics_cache_set(self, cache_key: str, analytics: PaymentAnalytics) -> None:
        with _ANALYTICS_CACHE_LOCK:
            _ANALYTICS_CACHE[cache_key] = (time.time(), analytics)

    def _row_coverage_status(self, row: TenantPayment) -> str:
        """paid/partial/unpaid/overdue для строки реестра, для аналитики и
        отображения. overdue (по due_date) всегда важнее суммы покрытия.

        needs_review (только xlsx-строки, см. xlsx_import/normalize.py._status)
        — та же приоритетность, что overdue: amount/paid_amount для такой
        строки сами не заслуживают доверия (0 там — "неизвестно", не "оплачено"
        или "не оплачено"), пересчёт по сумме покрытия ниже дал бы неверный
        unpaid/paid вместо честного "требует проверки"."""
        stored = (
            row.status.value if hasattr(row.status, "value") else str(row.status or "")
        ).lower()
        if stored in (PaymentStatus.OVERDUE.value, PaymentStatus.NEEDS_REVIEW.value):
            return stored
        if row.amount is not None and row.paid_amount is not None:
            # Сумма оплаты известна — статус по покрытию точнее сохранённого
            # значения (могло устареть между синками).
            return payment_coverage_status(row.amount, row.paid_amount)
        if row.paid_at and stored in ("unpaid", "none", ""):
            # Легаси-строки без paid_amount (до этой миграции): факт оплаты
            # известен только по paid_at.
            return PaymentStatus.PAID.value
        return stored or PaymentStatus.UNPAID.value

    def _build_payment_analytics(
        self,
        *,
        total: int,
        paid: int,
        unpaid: int,
        overdue: int,
        source: str,
        partial: int = 0,
        needs_review: int = 0,
        service_types_present: Optional[List[str]] = None,
    ) -> PaymentAnalytics:
        return PaymentAnalytics(
            total_tenants=total,
            total_invoices=total,
            paid=paid,
            partial=partial,
            unpaid=unpaid,
            overdue=overdue,
            needs_review=needs_review,
            source=source,
            service_types_present=service_types_present or [],
        )

    def _service_types_present(self, filters: PaymentFilter) -> List[str]:
        """service_type, реально встречающиеся хоть в одном счёте для тенанта/
        периода — НЕ сужено по filters.service_type (иначе выбор одного типа
        схлопывал бы список для фильтра до этого же одного типа). Дедуп по
        invoice_id тут не нужен — для "существует ли хоть один" дубли не
        меняют ответ, а distinct-запрос дешевле полного набора строк."""
        type_agnostic = filters.model_copy(update={"service_type": None, "status": None})
        query = self._apply_payment_filters(self.db.query(TenantPayment), type_agnostic)
        raw_values = (
            query.filter(
                TenantPayment.invoice_id.isnot(None),
                TenantPayment.invoice_id != "",
                TenantPayment.service_type.isnot(None),
            )
            .with_entities(TenantPayment.service_type)
            .distinct()
            .all()
        )
        found: set[str] = set()
        for (raw,) in raw_values:
            for part in (raw or "").split(","):
                part = part.strip()
                if part and part != "unknown":
                    found.add(part)
        from app.services.invoice_service_type import SERVICE_TYPE_ORDER

        return [t for t in SERVICE_TYPE_ORDER if t in found]

    def _dedupe_latest_per_invoice(self, rows: List[TenantPayment]) -> List[TenantPayment]:
        """Одна строка на реальный счёт — та же дедупликация по invoice_id, что
        уже используется в _get_analytics_from_db() для карточек аналитики
        ("считаем уникальные счета в реестре, а не все строки").

        get_payments() раньше отдавал ВСЕ строки TenantPayment как есть: и
        строки-дубликаты на один и тот же invoice_id (напр. заглушка,
        созданная /notifications/send до синка, рядом с уже засинканной
        полной строкой того же счёта — см. фикс 0f1d155 про
        case-insensitive поиск invoice_id, который такие дубли не
        предотвращает, только не создаёт новые), и строки вовсе без
        invoice_id. Из-за этого число строк в таблице реестра расходилось с
        карточками аналитики — реальный кейс на проде: карточка "Не
        оплачено" показывает 188, а под ней в таблице "Показано 1–20 из
        263". Строки без invoice_id аналитика не считает вовсе (см. фильтр
        invoice_id.isnot(None) в _get_analytics_from_db) — здесь тоже
        исключаем их, чтобы числа совпадали.

        Из пары дублей выбираем не просто "более новую по id/дате" строку, а
        более ПОЛНУЮ (есть amount, есть service_type) — иначе заглушка,
        созданная позже настоящего синка (см. app/api/notifications.py,
        payment_service.ensure_payment_for_counterparty), выигрывала бы у
        уже полностью засинканной строки того же счёта и в реестре опять
        было бы пусто там, где данные на самом деле есть."""
        def _rank(row: TenantPayment) -> tuple:
            return (
                row.amount is not None,
                bool((row.service_type or "").strip()),
                row.invoice_date or date.min,
                row.id or 0,
            )

        latest_by_invoice: dict[str, TenantPayment] = {}
        for row in sorted(rows, key=_rank, reverse=True):
            inv_key = (row.invoice_id or "").strip().lower()
            if not inv_key or inv_key in latest_by_invoice:
                continue
            latest_by_invoice[inv_key] = row
        return list(latest_by_invoice.values())

    def _analytics_scope_filters(self, filters: PaymentFilter) -> PaymentFilter:
        """Карточки аналитики всегда по всем статусам; status — только для таблицы."""
        return PaymentFilter(
            period=filters.period,
            date_from=filters.date_from,
            date_to=filters.date_to,
            ip_name=filters.ip_name,
            tenant_name=filters.tenant_name,
            status=None,
            service_type=filters.service_type,
            page=filters.page,
            page_size=filters.page_size,
        )

    def _invoice_in_period_month(self, invoice_date, period: Optional[str]) -> bool:
        if not period or len(period) != 7 or period[4] != "-":
            return True
        if not invoice_date:
            return False
        try:
            year_i, month_i = int(period[:4]), int(period[5:7])
        except ValueError:
            return True
        if hasattr(invoice_date, "year"):
            return invoice_date.year == year_i and invoice_date.month == month_i
        raw = str(invoice_date).split("T")[0]
        if raw.startswith(period):
            return True
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d").date()
            return parsed.year == year_i and parsed.month == month_i
        except ValueError:
            return False

    def _get_analytics_from_live_invoices(
        self,
        period: str,
        tenant_name_filter: Optional[str] = None,
    ) -> Optional[PaymentAnalytics]:
        """Сводка по счетам из 1С (как fetch_payments / sync), а не по строкам БД."""
        if not self.integration_1c or not self.integration_1c.client:
            return None
        try:
            items = self.integration_1c.fetch_payments(
                period,
                due_day=self._tenant_due_day(),
                utilities_due_day=self._tenant_utilities_due_day(),
                operations_due_day=self._tenant_operations_due_day(),
            )
        except Exception as exc:
            logger.warning("Live invoice analytics failed tenant_id=%s period=%s: %s", self.tenant_id, period, exc)
            return None
        if not items:
            return None

        tenant_filter = (tenant_name_filter or "").strip()
        if tenant_filter in ("Все", "All"):
            tenant_filter = ""
        # tenant_id уже ограничивает выборку арендатором каталога; имя каталога ≠ контрагент.
        if self.tenant_id:
            tenant_filter = ""

        paid = unpaid = overdue = 0
        belongs = getattr(self.integration_1c.client, "_invoice_belongs_to_period", None)
        for item in items:
            inv_date = item.get("invoice_date")
            due_date = item.get("due_date")
            inv_date_str = inv_date.isoformat() if hasattr(inv_date, "isoformat") else inv_date
            due_date_str = due_date.isoformat() if hasattr(due_date, "isoformat") else due_date
            if belongs:
                if not belongs(inv_date_str, due_date_str, period):
                    continue
            elif not self._invoice_in_period_month(inv_date, period):
                continue
            name = (item.get("tenant_name") or "").strip()
            if tenant_filter and tenant_filter.lower() not in name.lower():
                continue
            status = self._status_from_sync_item(item)
            if status == PaymentStatus.PAID:
                paid += 1
            elif status == PaymentStatus.OVERDUE:
                overdue += 1
            else:
                unpaid += 1

        total = paid + unpaid + overdue
        if total == 0:
            return None
        return self._build_payment_analytics(
            total=total,
            paid=paid,
            unpaid=unpaid,
            overdue=overdue,
            source="1c",
        )

    def _get_analytics_from_db(self, filters: PaymentFilter) -> PaymentAnalytics:
        """Fallback: считаем уникальные счета в реестре, а не все строки."""
        scope = self._analytics_scope_filters(filters)
        query = self._apply_payment_filters(self.db.query(TenantPayment), scope)
        rows = (
            query.filter(
                TenantPayment.invoice_id.isnot(None),
                TenantPayment.invoice_id != "",
            )
            .order_by(
                TenantPayment.invoice_date.desc(),
                TenantPayment.id.desc(),
            )
            .all()
        )

        if not filters.date_from and not filters.date_to and filters.period:
            rows = [row for row in rows if (row.period or "") == filters.period]

        tenant_filter = (filters.tenant_name or "").strip()
        if tenant_filter in ("Все", "All"):
            tenant_filter = ""
        if self.tenant_id:
            tenant_filter = ""
        if tenant_filter:
            rows = [
                row
                for row in rows
                if tenant_filter.lower() in (row.tenant_name or "").lower()
            ]

        paid = partial = unpaid = overdue = needs_review = 0
        for row in self._dedupe_latest_per_invoice(rows):
            status = self._row_coverage_status(row)
            if status == PaymentStatus.PAID.value:
                paid += 1
            elif status == PaymentStatus.PARTIAL.value:
                partial += 1
            elif status == PaymentStatus.OVERDUE.value:
                overdue += 1
            elif status == PaymentStatus.NEEDS_REVIEW.value:
                # Не в unpaid: сумма покрытия для этих строк сама не заслуживает
                # доверия (см. _row_coverage_status) — лумповать их в unpaid
                # означало бы врать в карточке дашборда так же, как раньше
                # врал статус PAID до появления needs_review.
                needs_review += 1
            else:
                unpaid += 1

        total = paid + partial + unpaid + overdue + needs_review
        return self._build_payment_analytics(
            total=total,
            paid=paid,
            partial=partial,
            unpaid=unpaid,
            overdue=overdue,
            needs_review=needs_review,
            source="database",
            service_types_present=self._service_types_present(filters),
        )

    def _load_counterparty_maps_for_sync(
        self,
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        """
        Сначала справочник контрагентов (id → имя, имя → id, БИН → id).
        Live из 1С, иначе кэш; без справочника счета не привяжем надёжно.
        """
        from app.models.counterparty_cache import CounterpartyCache
        from app.services.counterparty_name_match import (
            build_bin_resolution_index,
            load_cache_name_maps,
        )

        rows: list[dict] = []
        client = self.integration_1c.client if self.integration_1c else None
        if client and hasattr(client, "get_counterparties"):
            try:
                if hasattr(client, "authenticate") and not getattr(
                    client, "access_token", True
                ):
                    client.authenticate()
                cps = client.get_counterparties(limit=10000)
                for cp in cps or []:
                    cp_id = (getattr(cp, "id", None) or "").strip()
                    if not cp_id:
                        continue
                    rows.append(
                        {
                            "id": cp_id,
                            "fullName": (
                                getattr(cp, "full_name", None)
                                or getattr(cp, "name", None)
                                or ""
                            ),
                            "bin": getattr(cp, "bin", None) or "",
                            "iin": getattr(cp, "iin", None) or "",
                        }
                    )
                logger.info(
                    "Payment sync: loaded %s counterparties from 1C tenant_id=%s",
                    len(rows),
                    self.tenant_id,
                )
            except Exception as exc:
                logger.warning(
                    "Payment sync: live counterparties failed tenant_id=%s: %s",
                    self.tenant_id,
                    exc,
                )

        if not rows and self.tenant_id:
            cache_row = (
                self.db.query(CounterpartyCache)
                .filter(CounterpartyCache.tenant_id == self.tenant_id)
                .first()
            )
            if cache_row and isinstance(cache_row.data, list):
                rows = [cp for cp in cache_row.data if isinstance(cp, dict)]
                logger.info(
                    "Payment sync: loaded %s counterparties from cache tenant_id=%s",
                    len(rows),
                    self.tenant_id,
                )

        name_index, names_by_id = load_cache_name_maps(rows)
        bin_index = build_bin_resolution_index(rows)
        return name_index, names_by_id, bin_index

    def sync_from_1c(self, period: str) -> List[TenantPayment]:
        """
        Порядок: 1) контрагенты + id, 2) счета из 1С, 3) привязка счёта к cp_id.
        Upsert только по invoice_id — несколько счетов на одного контрагента за период.
        """
        from app.services.counterparty_name_match import bind_invoice_to_counterparty

        name_index, names_by_id, bin_index = self._load_counterparty_maps_for_sync()

        data_from_1c = self.integration_1c.fetch_payments(
            period,
            due_day=self._tenant_due_day(),
            utilities_due_day=self._tenant_utilities_due_day(),
            operations_due_day=self._tenant_operations_due_day(),
        )
        tenant = get_tenant_by_id(self.db, self.tenant_id)
        catalog_ip_name = tenant.legal_name if tenant else None

        payments = []
        skipped_no_invoice = 0
        for item in data_from_1c:
            invoice_id = (item.get("invoice_id") or "").strip()
            if not invoice_id:
                skipped_no_invoice += 1
                continue

            ip_name = catalog_ip_name or item.get("ip_name")
            bound_cp_id, display_name = bind_invoice_to_counterparty(
                counterparty_id=item.get("counterparty_id"),
                tenant_name=item.get("tenant_name"),
                name_index=name_index,
                names_by_id=names_by_id,
                bin_index=bin_index,
                bin_value=item.get("bin") or item.get("БИН"),
            )
            tenant_name = display_name or item.get("tenant_name") or ""
            counterparty_id = bound_cp_id or item.get("counterparty_id")

            # tenant_id обязателен в этих lookup'ах, когда он у нас есть: раньше
            # искали существующую строку только по invoice_id, без привязки к
            # арендатору — если у двух разных 1С-организаций (COM/Nova ids не
            # гарантированно глобально уникальны) совпадал invoice_id, sync
            # одного арендатора мог молча перезаписать чужую запись (см. аудит
            # от 2026-08-25). self.tenant_id может быть None только для
            # легаси/глобального sync без привязки к конкретному арендатору —
            # тогда сохраняем старое поведение (иначе не с чем сопоставлять).
            inv_key = invoice_id.lower()
            existing_query = self.db.query(TenantPayment).filter(
                func.lower(TenantPayment.invoice_id) == inv_key
            )
            if self.tenant_id:
                existing_query = existing_query.filter(TenantPayment.tenant_id == self.tenant_id)
            existing = existing_query.first()
            if not existing:
                existing_query = self.db.query(TenantPayment).filter(
                    TenantPayment.invoice_id == invoice_id,
                    TenantPayment.period == period,
                )
                if self.tenant_id:
                    existing_query = existing_query.filter(TenantPayment.tenant_id == self.tenant_id)
                existing = existing_query.first()

            if existing:
                existing.invoice_date = item["invoice_date"]
                existing.due_date = item["due_date"]
                existing.paid_at = item.get("paid_at")
                existing.amount = item.get("amount")
                existing.paid_amount = item.get("paid_amount")
                existing.status = self._status_from_sync_item(item)
                existing.invoice_id = invoice_id
                existing.period = period
                if item.get("service_type"):
                    existing.service_type = item["service_type"]
                if ip_name:
                    existing.ip_name = ip_name
                if counterparty_id:
                    existing.counterparty_id = counterparty_id
                if (tenant_name or "").strip():
                    existing.tenant_name = tenant_name
                if self.tenant_id and existing.tenant_id != self.tenant_id:
                    # Точечный backfill: строка была найдена по invoice_id
                    # (self.tenant_id раньше не проставлялся при sync).
                    existing.tenant_id = self.tenant_id
                payments.append(existing)
            else:
                payment = TenantPayment(
                    ip_name=ip_name,
                    tenant_name=tenant_name,
                    invoice_date=item["invoice_date"],
                    due_date=item["due_date"],
                    paid_at=item.get("paid_at"),
                    amount=item.get("amount"),
                    paid_amount=item.get("paid_amount"),
                    period=period,
                    status=self._status_from_sync_item(item),
                    invoice_id=invoice_id,
                    counterparty_id=counterparty_id,
                    tenant_id=self.tenant_id,
                    service_type=item.get("service_type"),
                )
                self.db.add(payment)
                payments.append(payment)

        if skipped_no_invoice:
            logger.warning(
                "Payment sync skipped %s rows without invoice_id tenant_id=%s period=%s",
                skipped_no_invoice,
                self.tenant_id,
                period,
            )

        self.db.commit()
        self._backfill_payment_fields_from_1c_index(period)
        self._backfill_counterparty_ids_from_names(period)
        return payments

    def _backfill_payment_fields_from_1c_index(self, period: str) -> int:
        """Заполнить пустые tenant_name / counterparty_id из batch invoices+payments (COM)."""
        if not self.tenant_id:
            return 0
        client = self.integration_1c.client if self.integration_1c else None
        if not client or not hasattr(client, "lookup_batch_invoice_header"):
            return 0

        query = self._scope_query_by_tenant(
            self.db.query(TenantPayment).filter(
                TenantPayment.period == period,
                TenantPayment.invoice_id.isnot(None),
                TenantPayment.invoice_id != "",
            )
        )

        rows = [
            row
            for row in query.all()
            if not (row.tenant_name or "").strip()
            or not (row.counterparty_id or "").strip()
        ]
        if not rows:
            return 0

        from app.services.counterparty_name_match import amounts_near

        headers_for_amount: list[dict] = []
        if hasattr(client, "batch_invoice_headers_for_backfill"):
            headers_for_amount = client.batch_invoice_headers_for_backfill()

        updated = 0
        for row in rows:
            changed = False
            header = None
            if (row.invoice_id or "").strip():
                header = client.lookup_batch_invoice_header(row.invoice_id)

            if not header and headers_for_amount and row.amount is not None:
                matches = [
                    h
                    for h in headers_for_amount
                    if amounts_near(row.amount, h.get("amount"))
                ]
                if len(matches) == 1:
                    header = matches[0]

            if not header:
                continue

            cp_name = (header.get("counterparty_name") or "").strip()
            cp_id = (header.get("counterparty_id") or "").strip()
            if cp_name and not (row.tenant_name or "").strip():
                row.tenant_name = cp_name
                changed = True
            if cp_id and not (row.counterparty_id or "").strip():
                row.counterparty_id = cp_id
                changed = True
            if changed:
                updated += 1

        if updated:
            self.db.commit()
            logger.info(
                "Backfilled payment CP fields from 1C index tenant_id=%s period=%s rows=%s",
                self.tenant_id,
                period,
                updated,
            )
        return updated

    def _backfill_counterparty_ids_from_names(self, period: str) -> int:
        """Заполнить counterparty_id по имени из кэша (однозначное совпадение)."""
        if not self.tenant_id:
            return 0
        from app.models.counterparty_cache import CounterpartyCache
        from app.services.counterparty_name_match import (
            load_cache_name_maps,
            resolve_to_cache_counterparty_id,
        )

        cache_row = (
            self.db.query(CounterpartyCache)
            .filter(CounterpartyCache.tenant_id == self.tenant_id)
            .first()
        )
        if not cache_row or not cache_row.data:
            return 0
        name_index, _ = load_cache_name_maps(cache_row.data)

        query = self._scope_query_by_tenant(
            self.db.query(TenantPayment).filter(
                TenantPayment.period == period,
                or_(
                    TenantPayment.counterparty_id.is_(None),
                    TenantPayment.counterparty_id == "",
                ),
            )
        )

        updated = 0
        for row in query.all():
            cp_id = resolve_to_cache_counterparty_id(row.tenant_name, name_index)
            if not cp_id:
                continue
            row.counterparty_id = cp_id
            updated += 1
        if updated:
            self.db.commit()
        return updated

    def _find_existing_payment(self, cp_key: str, invoice_id: str) -> Optional[TenantPayment]:
        # tenant_id — как в sync_from_1c: без него два арендатора с
        # совпадающим counterparty_id+invoice_id (не гарантированно глобально
        # уникальны для COM/Nova) могли получить/перезаписать чужую строку
        # (см. аудит от 2026-08-25).
        existing_query = self.db.query(TenantPayment).filter(
            func.lower(TenantPayment.counterparty_id) == cp_key,
            func.lower(TenantPayment.invoice_id) == invoice_id.strip().lower(),
        )
        if self.tenant_id:
            existing_query = existing_query.filter(TenantPayment.tenant_id == self.tenant_id)
        return existing_query.first()

    def ensure_payment_for_counterparty(
        self,
        counterparty_id: str,
        invoice_id: Optional[str] = None,
        *,
        integration: Optional[Integration1C] = None,
    ) -> TenantPayment:

        # Fast path — caller already knows the exact (counterparty_id,
        # invoice_id) pair, so the row is likely already sitting in the DB
        # (most callers here — bulk debtor send, auto-reminders — got both
        # straight off an existing TenantPayment row). Look it up BEFORE
        # requiring a live 1C client: incident 2026-09-03 — the bulk debtor
        # job required integration.client unconditionally here, so a single
        # flaky/unavailable 1C connection killed sends for payments we
        # already had locally and didn't need 1C for at all, while the
        # manual single-send path (which mostly hits this same "already
        # exists" case) kept working. Only a genuinely new payment (no local
        # row yet) needs the 1C round-trip below.
        if counterparty_id and invoice_id:
            existing = self._find_existing_payment(
                normalize_counterparty_id(counterparty_id), invoice_id
            )
            if existing:
                return existing

        integration = integration or self.integration_1c
        if not integration or not integration.client:
            raise HTTPException(status_code=503, detail="1C client not available")

        resolved_invoice_id, resolved_cp_id = resolve_invoice_for_counterparty(
            integration, invoice_id, counterparty_id
        )
        cp_key = normalize_counterparty_id(resolved_cp_id)

        existing = self._find_existing_payment(cp_key, resolved_invoice_id or "")
        if existing:
            return existing

        invoice = None
        for inv in integration.client.get_invoices(limit=50000):
            if (inv.id or "").strip().lower() == resolved_invoice_id.strip().lower():
                invoice = inv
                break
        if not invoice:
            raise HTTPException(status_code=404, detail="Счёт не найден в 1С")

        invoice_date = integration._parse_date(invoice.date)
        due_date = integration._calculate_due_date(invoice_date, self._tenant_due_day())
        amount_val = int(float(invoice.amount)) if invoice.amount is not None else None
        paid_amount_val = (
            int(float(invoice.paid_amount))
            if getattr(invoice, "paid_amount", None)
            else None
        )
        coverage = payment_coverage_status(
            float(invoice.amount or 0), float(invoice.paid_amount or 0)
        )
        paid_at = datetime.utcnow() if coverage == "paid" else None
        if coverage == "paid":
            status = PaymentStatus.PAID
        elif date.today() > due_date:
            status = PaymentStatus.OVERDUE
        elif coverage == "partial":
            status = PaymentStatus.PARTIAL
        else:
            status = PaymentStatus.UNPAID

        tenant = get_tenant_by_id(self.db, self.tenant_id)
        ip_name = tenant.legal_name if tenant else (invoice.counterparty_name or "—")
        period = invoice_date.strftime("%Y-%m")
        service_types = resolve_invoice_service_types(getattr(invoice, "items", None) or [])

        payment = TenantPayment(
            ip_name=ip_name,
            tenant_name=invoice.counterparty_name or resolved_cp_id,
            invoice_date=invoice_date,
            due_date=due_date,
            paid_at=paid_at,
            amount=amount_val,
            paid_amount=paid_amount_val,
            period=period,
            status=status,
            invoice_id=resolved_invoice_id,
            counterparty_id=resolved_cp_id,
            tenant_id=self.tenant_id,
            service_type=format_service_types_label(service_types),
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def get_test_payments(self) -> List[TenantPayment]:


        
        today = date.today()
        period = today.strftime("%Y-%m")
        
        test_payments = [
            TenantPayment(
                id=1,
                ip_name="Тест ИП",
                tenant_name="Тест Арендатор 1",
                invoice_date=today - timedelta(days=10),
                due_date=today - timedelta(days=5),
                paid_at=datetime.combine(today - timedelta(days=3), datetime.min.time()),
                status=PaymentStatus.PAID,
                period=period,
                amount=100000
            ),
            TenantPayment(
                id=2,
                ip_name="Тест ИП",
                tenant_name="Тест Арендатор 2",
                invoice_date=today - timedelta(days=10),
                due_date=today + timedelta(days=5),
                paid_at=None,
                status=PaymentStatus.UNPAID,
                period=period,
                amount=150000
            ),
            TenantPayment(
                id=3,
                ip_name="Тест ИП",
                tenant_name="Тест Арендатор 3",
                invoice_date=today - timedelta(days=20),
                due_date=today - timedelta(days=10),
                paid_at=None,
                status=PaymentStatus.OVERDUE,
                period=period,
                amount=200000
            ),
            TenantPayment(
                id=4,
                ip_name="Тест ИП",
                tenant_name="Тест Арендатор 4",
                invoice_date=today - timedelta(days=25),
                due_date=today - timedelta(days=15),
                paid_at=None,
                status=PaymentStatus.OVERDUE,
                period=period,
                amount=250000
            ),
        ]
        
        return test_payments
    
    def get_test_notifications(self, payment_id: int) -> List:


        notifications = []
        
        if payment_id == 1:
            notifications = [
                Notification(
                    id=1,
                    payment_id=payment_id,
                    notification_type=NotificationType.WEEK_BEFORE,
                    status=NotificationStatus.DELIVERED,
                    sent_at=datetime.utcnow(),
                    delivered_at=datetime.utcnow(),
                ),
                Notification(
                    id=2,
                    payment_id=payment_id,
                    notification_type=NotificationType.THREE_DAYS,
                    status=NotificationStatus.DELIVERED,
                    sent_at=datetime.utcnow(),
                    delivered_at=datetime.utcnow()
                ),
            ]
        elif payment_id == 2:
            notifications = [
                Notification(
                    id=3,
                    payment_id=payment_id,
                    notification_type=NotificationType.WEEK_BEFORE,
                    status=NotificationStatus.SENT,
                    sent_at=datetime.utcnow()
                ),
            ]
        elif payment_id in [3, 4]:
            notifications = [
                Notification(
                    id=4,
                    payment_id=payment_id,
                    notification_type=NotificationType.OVERDUE,
                    status=NotificationStatus.SENT,
                    sent_at=datetime.utcnow()
                ),
            ]
        
        return notifications
    
    def get_payments(self, filters: PaymentFilter, status_param: Optional[str] = None) -> tuple[List[TenantPayment], int]:


        if self.is_test_mode(filters, status_param):
            test_payments = self.get_test_payments()

            offset = (filters.page - 1) * filters.page_size
            paginated_payments = test_payments[offset:offset + filters.page_size]
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Test mode: returning {len(paginated_payments)} test payments out of {len(test_payments)}")
            return paginated_payments, len(test_payments)

        # paid/partial/unpaid считаются по покрытию суммы (см. _row_coverage_status),
        # а не по колонке status — она может быть устаревшей между синками. Тот же
        # принцип уже используется для карточек аналитики (_analytics_scope_filters).
        # overdue — исключение, доверяем сохранённому статусу как есть.
        coverage_statuses = (PaymentStatus.PAID, PaymentStatus.PARTIAL, PaymentStatus.UNPAID)
        if filters.status in coverage_statuses:
            scope = self._analytics_scope_filters(filters)
            query = self._apply_payment_filters(self.db.query(TenantPayment), scope)
            all_rows = self._dedupe_latest_per_invoice(query.all())
            matched = [
                row for row in all_rows
                if self._row_coverage_status(row) == filters.status.value
            ]
            matched.sort(key=lambda r: r.due_date, reverse=True)
            total = len(matched)
            offset = (filters.page - 1) * filters.page_size
            payments = matched[offset:offset + filters.page_size]
            self._enrich_payment_tenant_names(payments)
            return payments, total

        # Дедупликация по invoice_id (см. _dedupe_latest_per_invoice) требует
        # видеть все строки сразу — постранично на уровне SQL (offset/limit)
        # тут не выйдет, дубль того же счёта может оказаться на другой
        # странице. Объём тот же, что уже грузит ветка выше (все счета
        # тенанта за период), так что это не новый по масштабу запрос.
        query = self._apply_payment_filters(self.db.query(TenantPayment), filters)
        all_rows = self._dedupe_latest_per_invoice(query.all())
        all_rows.sort(key=lambda r: r.due_date, reverse=True)

        total = len(all_rows)

        offset = (filters.page - 1) * filters.page_size
        payments = all_rows[offset:offset + filters.page_size]
        self._enrich_payment_tenant_names(payments)

        return payments, total

    def _enrich_payment_tenant_names(self, payments: List[TenantPayment]) -> None:
        """Имена контрагентов из кэша, если в tenant_payments пусто (COM batch)
        ИЛИ это техническая заглушка — tenant_name совпадает с counterparty_id.

        Заглушки создаются в двух местах (app/api/notifications.py при первом
        "Отправить" по ещё не синканному счёту, payment_service.ensure_payment_for_counterparty)
        по паттерну `tenant_name = counterparty_name or counterparty_id`: если 1С
        не вернул человекочитаемое имя для этого конкретного документа, в
        tenant_name попадает сырой GUID. Раньше проверка "пусто ли tenant_name"
        такие строки не трогала (GUID — непустая строка), и клиент видел в
        реестре "2c68fb5c-5012-11f0-8725-5254001b9c43" вместо имени контрагента,
        пока обычный sync_from_1c не находил и не перезаписывал ту же строку."""
        if not payments:
            return
        cp_meta = self._counterparty_meta_index()
        if not cp_meta:
            return
        # id → name
        for payment in payments:
            cp_key = (payment.counterparty_id or "").strip().lower()
            current = (payment.tenant_name or "").strip()
            is_placeholder = not current or (cp_key and current.lower() == cp_key)
            if not is_placeholder:
                continue
            meta = cp_meta.get(cp_key)
            if meta and meta.get("name"):
                payment.tenant_name = meta["name"]
        # Для строк без counterparty_id имена не восстановить из кэша по id —
        # sync должен заполнять tenant_name из 1С (payments script / orphan).


    def _counterparty_meta_index(self) -> dict[str, dict[str, str]]:
        """БИН/имя из кэша контрагентов (быстро, без 1С)."""
        if not self.tenant_id:
            return {}
        from app.models.counterparty_cache import CounterpartyCache

        row = (
            self.db.query(CounterpartyCache)
            .filter(CounterpartyCache.tenant_id == self.tenant_id)
            .first()
        )
        index: dict[str, dict[str, str]] = {}
        if not row or not row.data:
            return index
        for cp in row.data:
            cp_id = (cp.get("id") or "").strip().lower()
            if not cp_id:
                continue
            index[cp_id] = {
                "name": (cp.get("fullName") or "").strip(),
                "bin": (cp.get("bin") or cp.get("iin") or "").strip(),
            }
        return index

    def list_invoices_from_db(
        self,
        period: Optional[str],
        *,
        counterparty_id: Optional[str] = None,
        limit: int = 10000,
    ) -> List[dict]:
        """Список счетов из tenant_payments (как реестр оплат) — без live-запроса в 1С."""
        query = self._scope_query_by_tenant(
            self.db.query(TenantPayment).filter(
                TenantPayment.invoice_id.isnot(None),
                TenantPayment.invoice_id != "",
            )
        )
        if period:
            query = query.filter(TenantPayment.period == period)
        if counterparty_id:
            cp_key = normalize_counterparty_id(counterparty_id)
            query = query.filter(
                func.lower(TenantPayment.counterparty_id) == cp_key
            )

        rows = (
            query.order_by(
                TenantPayment.invoice_date.desc(),
                TenantPayment.id.desc(),
            )
            .limit(max(1, min(limit, 50000)))
            .all()
        )
        cp_meta = self._counterparty_meta_index()
        cache_data = []
        if self.tenant_id:
            from app.models.counterparty_cache import CounterpartyCache
            from app.services.counterparty_name_match import (
                load_cache_name_maps,
                resolve_to_cache_counterparty_id,
            )

            cache_row = (
                self.db.query(CounterpartyCache)
                .filter(CounterpartyCache.tenant_id == self.tenant_id)
                .first()
            )
            if cache_row and cache_row.data:
                cache_data = cache_row.data
        name_index, names_by_id = (
            load_cache_name_maps(cache_data) if cache_data else ({}, {})
        )
        # name -> id для строк без counterparty_id (COM Maxi Mall)
        name_to_cp: dict[str, dict[str, str]] = {}
        for cp_id, meta in cp_meta.items():
            nm = " ".join((meta.get("name") or "").lower().split())
            if nm and nm not in name_to_cp:
                name_to_cp[nm] = {"id": cp_id, **meta}

        invoices: List[dict] = []
        for payment in rows:
            cp_id = (payment.counterparty_id or "").strip()
            cp_key = cp_id.lower()
            meta = cp_meta.get(cp_key, {})
            if not meta and cache_data:
                matched = resolve_to_cache_counterparty_id(payment.tenant_name, name_index)
                if matched:
                    cp_key = matched
                    meta = cp_meta.get(cp_key, {})
                    if not meta:
                        meta = {
                            "name": names_by_id.get(cp_key, payment.tenant_name or ""),
                            "bin": "",
                        }
            if not meta:
                nm = " ".join((payment.tenant_name or "").lower().split())
                meta = name_to_cp.get(nm, {})
                if meta.get("id") and not cp_id:
                    cp_id = meta["id"]
            cp_name = meta.get("name") or payment.tenant_name or ""
            status = (
                payment.status.value
                if hasattr(payment.status, "value")
                else str(payment.status or "unpaid")
            )
            if isinstance(status, str):
                status = status.lower()
            inv_date = payment.invoice_date.isoformat() if payment.invoice_date else ""
            amount = float(payment.amount or 0)
            invoices.append(
                {
                    "id": payment.invoice_id,
                    "number": payment.invoice_id or "",
                    "date": inv_date,
                    "counterparty_name": cp_name,
                    "counterparty_id": cp_id,
                    "counterparty": {
                        "id": cp_id,
                        "name": cp_name,
                        "bin": meta.get("bin") or "",
                    },
                    "amount": amount,
                    "currency": "KZT",
                    "status": status,
                    "paid_amount": amount if status == "paid" else None,
                    "items": [],
                    # invoice-client needs this to pick the right download
                    # endpoint (see xlsx_invoice_pdf.py's module docstring —
                    # this "id" is payment.invoice_id, which for a
                    # source="xlsx" row is a synthetic "xlsx:..." key that
                    # /1c/invoices/{id}/download will always reject).
                    "source": payment.source or "one_c",
                }
            )
        return invoices

    def _coerce_date(self, value) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        raw = str(value).strip().split("T")[0]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _coerce_datetime(self, value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        raw = str(value).strip()
        if "T" in raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                raw = raw.split("T")[0]
        try:
            return datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None

    def _payment_type_label_for_invoice(
        self,
        invoice_id: Optional[str],
        tenant=None,
    ) -> str:
        if not invoice_id:
            return "—"
        client = self.integration_1c.client
        if not client or not hasattr(client, "fetch_invoice_line_items"):
            return "—"
        try:
            from app.services.invoice_service_type import (
                resolve_invoice_service_types,
                tenant_payment_keywords,
            )

            items = client.fetch_invoice_line_items(invoice_id)
            types = resolve_invoice_service_types(
                items,
                keywords=tenant_payment_keywords(tenant),
            )
            if not types:
                return "—"
            return ", ".join(_PAYMENT_TYPE_LABELS.get(t, t) for t in types)
        except Exception as exc:
            logger.debug("Export payment type for %s failed: %s", invoice_id, exc)
            return "—"

    def _tenant_payment_to_row(self, payment: TenantPayment) -> dict:
        status = payment.status.value if hasattr(payment.status, "value") else str(payment.status)
        return {
            "ip_name": payment.ip_name,
            "tenant_name": payment.tenant_name,
            "invoice_date": payment.invoice_date,
            "due_date": payment.due_date,
            "status": status,
            "paid_at": payment.paid_at,
            "amount": payment.amount,
            "invoice_id": payment.invoice_id,
        }

    def _export_rows_from_registry_db(
        self,
        filters: PaymentFilter,
        status_param: Optional[str] = None,
    ) -> List[dict]:
        """Строки Excel из tenant_payments (реестр на вкладке «Оплаты»)."""
        export_filters = PaymentFilter(
            period=filters.period,
            date_from=filters.date_from,
            date_to=filters.date_to,
            ip_name=filters.ip_name,
            tenant_name=filters.tenant_name,
            status=filters.status,
            page=1,
            page_size=10000,
        )
        payments, _ = self.get_payments(export_filters, status_param)
        return [self._tenant_payment_to_row(p) for p in payments]

    def _export_rows_from_com_db(
        self,
        filters: PaymentFilter,
        status_param: Optional[str] = None,
        tenant=None,
    ) -> List[dict]:
        """COM: как OData по структуре (контрагент × последний счёт за период), но из БД после sync."""
        from app.models.counterparty_cache import CounterpartyCache
        from app.services.counterparty_cache_service import _resolve_invoice_status_by_cp

        if not self.tenant_id:
            return []

        row = (
            self.db.query(CounterpartyCache)
            .filter(CounterpartyCache.tenant_id == self.tenant_id)
            .first()
        )
        cache_items = list(row.data or []) if row and row.data else []
        if not cache_items:
            return []

        ip_name = (getattr(tenant, "legal_name", None) or "").strip() if tenant else ""
        if not ip_name and filters.ip_name and filters.ip_name not in ("Все", "All"):
            ip_name = filters.ip_name

        status_by_cp = _resolve_invoice_status_by_cp(
            self.db,
            tenant_id=self.tenant_id,
            tenant=tenant,
            period=filters.period,
        )
        status_filter = filters.status.value if filters.status else None
        tenant_filter = (filters.tenant_name or "").strip()
        if tenant_filter in ("Все", "All"):
            tenant_filter = ""

        rows: List[dict] = []
        for cp in cache_items:
            full_name = (cp.get("fullName") or "").strip()
            if not full_name or full_name.startswith("Индивидуальные предприниматели"):
                continue
            if tenant_filter and tenant_filter.lower() not in full_name.lower():
                continue

            cp_key = (cp.get("id") or "").strip().lower()
            latest = status_by_cp.get(cp_key) or {}
            payment_status = str(latest.get("paymentStatus") or "unpaid").lower()
            if status_filter and payment_status != status_filter:
                continue

            rows.append(
                {
                    "ip_name": ip_name or "—",
                    "tenant_name": full_name,
                    "invoice_date": self._coerce_date(latest.get("invoiceDate")),
                    "due_date": self._coerce_date(latest.get("dueDate")),
                    "status": payment_status,
                    "paid_at": self._coerce_datetime(latest.get("paidAt")),
                    "amount": latest.get("amount"),
                    "invoice_id": latest.get("invoiceId"),
                }
            )
        return rows

    def _export_rows_from_1c(
        self,
        filters: PaymentFilter,
        status_param: Optional[str] = None,
    ) -> List[dict]:
        client = self.integration_1c.client
        if not client or not hasattr(client, "get_latest_invoice_status_by_counterparty"):
            return []

        tenant = get_tenant_by_id(self.db, self.tenant_id) if self.tenant_id else None
        ip_name = tenant.legal_name if tenant else ""
        if not ip_name and filters.ip_name and filters.ip_name not in ("Все", "All"):
            ip_name = filters.ip_name

        try:
            status_by_cp = client.get_latest_invoice_status_by_counterparty(
                due_day=self._tenant_due_day(),
                utilities_due_day=self._tenant_utilities_due_day(),
                operations_due_day=self._tenant_operations_due_day(),
                period=filters.period,
            )
            counterparties = client.get_counterparties(limit=10000)
        except Exception as exc:
            logger.warning("1C export failed: %s", exc)
            return []

        status_filter = filters.status.value if filters.status else None
        tenant_filter = (filters.tenant_name or "").strip()
        if tenant_filter in ("Все", "All"):
            tenant_filter = ""
        rows: List[dict] = []
        for cp in counterparties:
            full_name = (cp.full_name or "").strip()
            if not full_name or full_name.startswith("Индивидуальные предприниматели"):
                continue
            if tenant_filter and tenant_filter.lower() not in full_name.lower():
                continue

            cp_key = (cp.id or "").strip().lower()
            latest = status_by_cp.get(cp_key) or {}
            payment_status = str(latest.get("paymentStatus") or "unpaid").lower()

            if status_filter and payment_status != status_filter:
                continue

            rows.append({
                "ip_name": ip_name or "—",
                "tenant_name": full_name,
                "invoice_date": self._coerce_date(latest.get("invoiceDate")),
                "due_date": self._coerce_date(latest.get("dueDate")),
                "status": payment_status,
                "paid_at": self._coerce_datetime(latest.get("paidAt")),
                "amount": latest.get("amount"),
                "invoice_id": latest.get("invoiceId"),
            })
        return rows

    def _enrich_export_rows_payment_types(
        self,
        rows: List[dict],
        tenant=None,
    ) -> List[dict]:
        # Each label does a live 1C line-items lookup (single call can block up to
        # the client's own ~120s timeout). With hundreds of rows and a degraded
        # 1C/Nova connector, that turned a single export into a 3+ minute request,
        # blowing past the frontend's 30s timeout. A between-rows deadline check
        # alone isn't enough — one slow call can itself exceed the whole budget —
        # so each lookup runs with its own hard timeout via a worker thread; once
        # the total budget is spent we stop waiting and fall back to "—".
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

        deadline = time.monotonic() + 8.0
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            for row in rows:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    row["payment_type"] = "—"
                    continue
                future = pool.submit(
                    self._payment_type_label_for_invoice,
                    row.get("invoice_id"),
                    tenant,
                )
                try:
                    row["payment_type"] = future.result(timeout=remaining)
                except FutureTimeoutError:
                    row["payment_type"] = "—"
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return rows

    def get_export_rows(
        self,
        filters: PaymentFilter,
        status_param: Optional[str] = None,
    ) -> List[dict]:
        """Строки для Excel: OData — live 1С; COM — БД после sync (как таблица контрагентов)."""
        tenant = get_tenant_by_id(self.db, self.tenant_id) if self.tenant_id else None
        if self.is_test_mode(filters, status_param):
            rows = [self._tenant_payment_to_row(p) for p in self.get_test_payments()]
            return self._enrich_export_rows_payment_types(rows, tenant)

        if tenant and tenant_uses_nova_org(tenant):
            rows = self._export_rows_from_com_db(filters, status_param, tenant)
            if not rows:
                rows = self._export_rows_from_registry_db(filters, status_param)
            return self._enrich_export_rows_payment_types(rows, tenant)

        from_1c = self._export_rows_from_1c(filters, status_param)
        if from_1c:
            return self._enrich_export_rows_payment_types(from_1c, tenant)

        rows = self._export_rows_from_registry_db(filters, status_param)
        return self._enrich_export_rows_payment_types(rows, tenant)

    def get_analytics(self, filters: PaymentFilter, status_param: Optional[str] = None) -> PaymentAnalytics:

        if self.is_test_mode(filters, status_param):

            return PaymentAnalytics(
                total_tenants=4,
                total_invoices=4,
                paid=1,
                unpaid=1,
                overdue=2,
                source="test",
            )

        if filters.period or filters.date_from or filters.date_to:
            scope = self._analytics_scope_filters(filters)
            cache_key = _analytics_cache_key(
                self.tenant_id,
                scope.period,
                scope.tenant_name,
                scope.ip_name,
                scope.date_from,
                scope.date_to,
                scope.service_type,
            )
            cached = self._analytics_cache_get(cache_key)
            if cached:
                return cached

        # Карточки аналитики — только из БД (после sync). Live 1С в HTTP давал 60–120 с,
        # ingress/nginx обрывает ~15 с → 504 и «ничего не грузится» на проде.
        analytics = self._get_analytics_from_db(self._analytics_scope_filters(filters))
        if filters.period or filters.date_from or filters.date_to:
            scope = self._analytics_scope_filters(filters)
            self._analytics_cache_set(
                _analytics_cache_key(
                    self.tenant_id,
                    scope.period,
                    scope.tenant_name,
                    scope.ip_name,
                    scope.date_from,
                    scope.date_to,
                    scope.service_type,
                ),
                analytics,
            )
        return analytics

    def warm_analytics_cache(self, period: str) -> None:
        """После sync: положить сводку из БД в in-memory кэш (быстрый ответ карточек)."""
        scope = self._analytics_scope_filters(
            PaymentFilter(period=period, page=1, page_size=1),
        )
        cache_key = _analytics_cache_key(
            self.tenant_id, scope.period, scope.tenant_name, scope.ip_name, service_type=scope.service_type
        )
        self._analytics_cache_set(cache_key, self._get_analytics_from_db(scope))

    def get_payment_scoped(self, payment_id: int) -> Optional[TenantPayment]:
        """Платёж по id, но только если он принадлежит self.tenant_id (когда он задан).

        Используется там, где payment_id приходит от клиента напрямую (например
        GET /api/payments/{id}/notifications) — без этой проверки один арендатор
        мог запросить чужой payment_id и получить чужие уведомления/номера
        телефонов (IDOR, см. аудит от 2026-08-25). tenant_id=None (админ/ТРЦ без
        конкретного арендатора) сохраняет прежний широкий доступ.
        """
        payment = self.db.query(TenantPayment).filter(TenantPayment.id == payment_id).first()
        if not payment:
            return None
        if self.tenant_id and payment.tenant_id != self.tenant_id:
            return None
        return payment

    def update_payment_status(self, payment_id: int) -> Optional[TenantPayment]:

        payment = self.db.query(TenantPayment).filter(TenantPayment.id == payment_id).first()
        if payment:
            payment.status = self.calculate_status(payment.due_date, payment.paid_at)
            self.db.commit()
            self.db.refresh(payment)
        return payment
