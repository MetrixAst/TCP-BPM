"""Классификация счёта: аренда / коммуналка / маркетинг (бывш. эксплуатация) /
вывеска / АССП — по названиям строк 1С. Плюс "debt"/"other" — не из 1С-строк,
а из xlsx-источников (см. app/services/xlsx_import/): их ни один документ 1С
классификатором ниже не породит сам, они выставляются explicitly импортёром.

5 1С-категорий подтверждены на реальных данных (ИП Ибрагимов, CityMall, счета
от 2026-08-20): "Размещение вывески" и "АССП. Возмещение затрат услуги
АССП." — обрати внимание, реальное написание "АССП" (два "С"), не "АСПП".
Ключевые слова глобальные и одинаковые для всех арендаторов — намеренное
решение: per-tenant переопределение уже когда-то было в схеме
(Tenant.payment_keywords_rent/utilities/operations), но отключено в
app/api/admin.py (администратор не может задать свои ключевые слова —
только встроенные дефолты), так что новые категории следуют тому же
принципу вместо частичного возврата к отключённому паттерну.

"debt"/"other" добавлены 2026-08-26 под xlsx-импорт (Maxi Mall: колонки
"Долг пред.периода"/"Прочее" в листах "Начисление <месяц>" — см. эталонный
парсер xlsx_import/parsers/maxi_mall.py). Не смэппены на "rent"/"operations",
хотя оба маршрута телефона существуют — "Долг пред.периода" это не всегда
именно аренда (может быть просроченная КУ), а сваливание его в "operations"
увело бы напоминание о реальном долге на контакт по эксплуатации/маркетингу,
которому это не по адресу. resolve_phone_for_service (см.
counterparty_phone_routing.py) не умеет их специально — для них уже есть
безопасный дефолт: первый телефон из общего списка, как для signage/assp.
tenant_due_day_for_service/due_day_for_service_type туда же — не
utilities/operations -> берут due-day аренды, тоже разумный дефолт без
доп. кода.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, List, Literal, Optional, Sequence

ServiceType = Literal[
    "rent", "utilities", "operations", "signage", "assp", "debt", "other", "unknown"
]

_DEFAULT_RENT = ("аренд",)
_DEFAULT_UTIL = ("коммун", "электр", "вода", "тепл", "тбо", "мусор", "канал", "интернет")
_DEFAULT_OPS = ("эксплуат", "маркетинг")
_DEFAULT_SIGNAGE = ("вывеск",)
_DEFAULT_ASSP = ("ассп",)

# Порядок для сортировки/отображения типов в одном счёте (см.
# format_service_types_label) — не алфавитный, а по частоте/важности.
# debt/other — в хвосте: 1С-путь их никогда не производит (см. модуль-докстринг),
# добавлены только чтобы упорядочить смешанный список, если он когда-нибудь
# встретится (сегодня xlsx-импортёр создаёт одну строку на один service_type,
# смешения не бывает).
SERVICE_TYPE_ORDER: tuple[ServiceType, ...] = (
    "rent",
    "utilities",
    "operations",
    "signage",
    "assp",
    "debt",
    "other",
)


@dataclass(frozen=True)
class PaymentKeywords:
    rent: tuple[str, ...]
    utilities: tuple[str, ...]
    operations: tuple[str, ...]
    signage: tuple[str, ...] = _DEFAULT_SIGNAGE
    assp: tuple[str, ...] = _DEFAULT_ASSP


DEFAULT_PAYMENT_KEYWORDS = PaymentKeywords(
    rent=_DEFAULT_RENT,
    utilities=_DEFAULT_UTIL,
    operations=_DEFAULT_OPS,
    signage=_DEFAULT_SIGNAGE,
    assp=_DEFAULT_ASSP,
)

# КНП (код назначения платежа) по типу услуги, когда его нет ни в самом
# документе 1С, ни в ручном фоллбеке тенанта (Tenant.invoice_payment_knp) —
# запрошено 2026-09-02: реальные 1С-документы (Astranium/Maxi Mall)
# сплошь и рядом просто не заполняют это поле, а старый единственный
# tenant.invoice_payment_knp одинаково применялся ко всем типам начисления
# (аренда/эксплуатация/коммуналка), хотя у них должны быть разные коды.
# signage/assp/debt/other/unknown сюда намеренно не входят — для них
# по-прежнему используется общий tenant.invoice_payment_knp (см.
# _merge_supplier_requisites), как и раньше.
# operations был 858 (2026-09-02), поменяно на 855 в тот же день по
# требованию менеджера Maxi Mall: эксплуатация и маркетинг должны идти под
# тем же кодом, что и аренда, не отдельным.
DEFAULT_KNP_BY_SERVICE_TYPE: dict[str, str] = {
    "rent": "855",
    "operations": "855",
    "utilities": "856",
}


def parse_keyword_list(raw: Optional[str]) -> Optional[tuple[str, ...]]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    parts = re.split(r"[,;\n]+", text.lower())
    out = tuple(p.strip() for p in parts if p.strip())
    return out or None


def tenant_payment_keywords(tenant: Any = None) -> PaymentKeywords:
    """Встроенные дефолты по названиям строк 1С (поля в админке не используются)."""
    return DEFAULT_PAYMENT_KEYWORDS


def _line_name(item: Any) -> str:
    if isinstance(item, dict):
        for key in (
            "name",
            "Содержание",
            "Номенклатура_Description",
            "Description",
            "Наименование",
        ):
            val = item.get(key)
            if isinstance(val, dict):
                val = val.get("Description") or val.get("Наименование") or val.get("name")
            if val and str(val).strip():
                return str(val).lower()
        return ""
    return str(getattr(item, "name", "") or "").lower()


def _matches_any(name: str, keywords: Sequence[str]) -> bool:
    return any(kw in name for kw in keywords)


def resolve_invoice_service_types(
    items: Sequence[Any],
    *,
    keywords: Optional[PaymentKeywords] = None,
) -> List[ServiceType]:
    """
    Типы услуг по строкам счёта (встроенные дефолты: аренд / коммун|электр|вода|...|интернет /
    эксплуат|маркетинг / вывеск / ассп). Один счёт может содержать строки нескольких
    типов сразу (напр. аренда + коммуналка в одном документе) — возвращаются все найденные,
    в порядке SERVICE_TYPE_ORDER.
    """
    kw = keywords or DEFAULT_PAYMENT_KEYWORDS
    found: set[ServiceType] = set()
    for item in items or []:
        name = _line_name(item)
        if not name.strip():
            continue
        if _matches_any(name, kw.rent):
            found.add("rent")
        if _matches_any(name, kw.utilities):
            found.add("utilities")
        if _matches_any(name, kw.operations):
            found.add("operations")
        if _matches_any(name, kw.signage):
            found.add("signage")
        if _matches_any(name, kw.assp):
            found.add("assp")

    return [t for t in SERVICE_TYPE_ORDER if t in found]


def format_service_types_label(types: Sequence[ServiceType]) -> str:
    """Значение, которое хранится в TenantPayment.service_type / отдаётся в API —
    типы через запятую (см. аудит-обсуждение от 2026-08-25: один счёт с
    несколькими типами — одна строка реестра, типы через запятую, а не
    разбивка на "виртуальные" строки). "unknown", если ни один не найден —
    не пустая строка, чтобы отличать "проверили, но не распознали" от "ещё
    не вычисляли" (NULL)."""
    return ",".join(types) if types else "unknown"


def parse_stored_service_types(raw: Optional[str]) -> List[ServiceType]:
    """Обратное к format_service_types_label — разобрать уже сохранённое
    TenantPayment.service_type ("rent,utilities", "unknown", NULL) обратно
    в список. Запрошено 2026-09-02: bulk_debtor_notify_service раньше на
    КАЖДЫЙ счёт заново ходил в живую 1С за типом строк
    (invoice_service_types_from_1c), хотя sync_from_1c уже давно посчитал
    и сохранил это же самое поле на payment.service_type — на медленной/
    нестабильной organizации (Maxi Mall) это и было причиной, почему
    ручная отправка одного счёта (тип уже известен из этого поля, в 1С
    ходить не нужно) работала, а массовая рассылка (шла в 1С на каждый из
    230+ счетов) висла или падала по таймауту. Теперь сначала пробуем это
    поле, и только если оно пусто/NULL/"unknown" (старая несинканная
    строка) — падаем на живой запрос, как раньше."""
    if not raw:
        return []
    found = {p.strip() for p in raw.split(",") if p.strip() and p.strip() != "unknown"}
    return [t for t in SERVICE_TYPE_ORDER if t in found]


def resolve_invoice_service_type(
    items: Sequence[Any],
    *,
    keywords: Optional[PaymentKeywords] = None,
) -> ServiceType:
    types = resolve_invoice_service_types(items, keywords=keywords)
    if not types:
        return "unknown"
    if len(types) == 1:
        return types[0]
    return types[0]


def tenant_due_day_for_service(tenant: Any, service_type: str, *, default: int = 5) -> int:
    if service_type == "utilities":
        raw = getattr(tenant, "invoice_due_day_utilities", None)
    elif service_type == "operations":
        raw = getattr(tenant, "invoice_due_day_operations", None)
    else:
        raw = getattr(tenant, "invoice_due_day", None)
    try:
        return max(1, min(31, int(raw or default)))
    except (TypeError, ValueError):
        return default


def due_day_for_service_type(
    service_type: str,
    *,
    rent: int,
    utilities: int,
    operations: int,
) -> int:
    if service_type == "utilities":
        return utilities
    if service_type == "operations":
        return operations
    return rent


def _day_in_month(year: int, month: int, day: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(1, day), last))


def due_date_in_invoice_month(inv_date: date, due_day: int) -> date:
    """Срок оплаты: due_day-е число, но всегда СТРОГО ПОЗЖЕ даты счёта.

    Для большинства счетов due_day (обычно 5) ещё не наступил на момент
    формирования счёта — тогда срок в том же месяце. Но если счёт
    сформирован уже после due_day текущего месяца (реальный кейс: счёт за
    аренду выставлен 20.08.2026, due_day=5 — 5-е число августа уже прошло),
    срок переносится на due_day СЛЕДУЮЩЕГО месяца.

    Раньше функция безусловно возвращала due_day текущего месяца, из-за
    чего клиентам уходили сообщения вида "Крайний срок оплаты: 05.08.2026"
    для счёта от 20.08.2026 — срок оплаты раньше даты самого счёта — и
    счета помечались "overdue" сразу же после синхронизации.
    """
    candidate = _day_in_month(inv_date.year, inv_date.month, due_day)
    if candidate > inv_date:
        return candidate
    if inv_date.month == 12:
        return _day_in_month(inv_date.year + 1, 1, due_day)
    return _day_in_month(inv_date.year, inv_date.month + 1, due_day)
