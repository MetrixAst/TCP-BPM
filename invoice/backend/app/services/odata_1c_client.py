from __future__ import annotations

"""
HTTP OData client for 1C:Enterprise (standard.odata).
Uses Basic Auth instead of REST /auth. Does not modify app/client_1c/.
"""
import logging
import re
import time
import calendar
from datetime import date, datetime, timedelta
from typing import List, Optional, Union
from urllib.parse import quote
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

from app.services.invoice_service_type import (
    due_day_for_service_type,
    due_date_in_invoice_month,
    resolve_invoice_service_types,
)
from app.services.payment_status_rules import paid_enough
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.safe_filename import safe_filename_component
from app.client_1c.exceptions import APIError, AuthenticationError, ValidationError
from app.client_1c.models import (
    AuthResponse,
    Balance,
    ConfirmResponse,
    Counterparty,
    DataResponse,
    Invoice,
    Payment,
)


def is_odata_url(url: str) -> bool:
    return bool(url) and "odata" in url.lower()


_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_guid(value: str) -> bool:
    return bool(value and _GUID_RE.match(value.strip()))


def _extract_guid_key(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if _looks_like_guid(raw):
        return raw.lower()
    match = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        raw,
        re.IGNORECASE,
    )
    return match.group(0).lower() if match else raw.lower()


def _guid_literal(value: str, field: str = "id") -> str:
    """Validates `value` is GUID-shaped before it's interpolated into an OData
    resource path as `guid'...'`.

    Several call sites used to build these paths by raw f-string interpolation
    of externally-supplied ids (e.g. invoice_id from a public download
    endpoint's path param) with no format check — a crafted value could break
    out of the quoted literal and reach the tenant's live 1C OData server
    verbatim (OData injection, see audit from 2026-08-25). Unlike
    `_extract_guid_key` (which is for *finding* a GUID inside a compound key
    and falls back to returning the raw string unchanged), this function is a
    hard boundary: it raises rather than silently passing through anything
    that isn't actually a GUID.
    """
    raw = (value or "").strip().strip("'\"")
    if not _looks_like_guid(raw):
        raise ValidationError(f"Invalid {field}: expected a GUID, got {value!r}")
    return raw.lower()


def _contact_owner_key(row: dict) -> str:
    for key in (
        "Объект",
        "Объект_Key",
        "Контрагент_Key",
        "Владелец_Key",
        "ОбъектВладелец",
        "ОбъектВладелец_Key",
    ):
        owner = _extract_guid_key(_first_str(row, key))
        if owner:
            return owner
    return ""


def _contact_kind_key(row: dict) -> str:
    for key in ("Вид_Key", "Вид", "ВидКонтактнойИнформации_Key", "Type"):
        kind = _extract_guid_key(_first_str(row, key))
        if kind:
            return kind
    return ""


def _looks_like_address(value: str) -> bool:
    text = (value or "").strip()
    if len(text) < 8:
        return False
    if re.fullmatch(r"[\d\s+\-()]+", text):
        return False
    markers = (
        "ул",
        "улиц",
        "пр",
        "просп",
        "дом",
        "кв",
        "офис",
        "г.",
        "город",
        "обл",
        "район",
        "республик",
        "казахстан",
        "алматы",
        "астана",
        "павлодар",
    )
    lower = text.lower()
    return any(m in lower for m in markers) or "," in text


def _first_str(row: dict, *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val)
    return ""


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 10:
        return ""
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return f"+{digits}" if digits else ""


def _phone_dedup_key(value: str) -> str:
    return _normalize_phone(value) or re.sub(r"\D", "", value or "")


def _contact_phone_display(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    label_part = re.sub(r"[\d\s+\-().,]", "", text)
    if re.search(r"[A-Za-zА-Яа-яЁё]", label_part):
        return text
    return _normalize_phone(text) or text


# Зеркалит OData1CClient.CONTACT_KIND_PHONE/CONTACT_KIND_MOBILE (стандартные для
# типовой 1С UUID видов контактной информации) — используются здесь как
# module-level значения, т.к. _extract_phone_from_row вызывается вне класса.
_CONTACT_KIND_PHONE = "c5bb357f-c3b0-48ba-8a12-a42cbf99a845"
_CONTACT_KIND_MOBILE = "f9e52726-2faf-4dca-85d0-559b80df2c53"


_NON_PHONE_TYPE_NAMES = ("адрес", "address", "электронная почта", "email", "e-mail")


def _extract_phone_from_row(row: dict) -> str:
    """Строка InformationRegister_КонтактнаяИнформация. Каждая строка несёт свой
    Тип/Вид (телефон/адрес/почта/...) — важно СНАЧАЛА проверить это, а не просто
    пытаться распарсить любое текстовое поле как телефон: адрес вида
    "г. Алматы, ул. …, тел. 87787897224" содержит цифры, которые старый
    ключ-по-имени-эвристика раньше принимала за номер телефона."""
    kind = str(row.get("Вид") or row.get("ВидКонтактнойИнформации") or "").strip()
    type_name = str(row.get("Тип") or row.get("type") or "").strip().lower()

    is_phone_typed = kind in (_CONTACT_KIND_PHONE, _CONTACT_KIND_MOBILE) or type_name in (
        "телефон",
        "phone",
        "мобильный",
    )
    is_other_typed = (not is_phone_typed) and (
        type_name in _NON_PHONE_TYPE_NAMES
        or (kind and kind not in (_CONTACT_KIND_PHONE, _CONTACT_KIND_MOBILE))
    )
    if is_other_typed:
        # Тип/Вид известен и явно не телефон (адрес и т.п.) — не гадать по тексту.
        return ""

    if is_phone_typed:
        # Строка явно помечена как телефон — доверяем Представлению, даже если
        # по имени ключа его не узнать (раньше такая строка с пустым
        # Представлением просто пропускалась целиком, хотя это законная,
        # просто неполная запись).
        for key in ("Представление", "presentation", "ТекстоваяСтрока", "Значение", "Value"):
            if key in row:
                phone = _normalize_phone(str(row.get(key) or ""))
                if phone:
                    return phone
        return ""

    # Тип/Вид отсутствуют в самой строке (не этот регистр, либо неполные данные) —
    # старая эвристика как резерв: по имени ключа, затем по общим текстовым полям.
    for key, val in row.items():
        if "@" in key or val is None:
            continue
        key_lower = key.lower()
        if any(
            token in key_lower
            for token in ("телефон", "phone", "mobile", "мобильн", "whatsapp")
        ):
            phone = _normalize_phone(str(val))
            if phone:
                return phone
    for key in ("ТекстоваяСтрока", "Значение", "Представление", "Value", "Description"):
        if key in row:
            phone = _normalize_phone(str(row.get(key) or ""))
            if phone:
                return phone
    return ""


def _first_float(row: dict, *keys: str) -> float:
    for key in keys:
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0


def _extract_vat_from_row(row: dict) -> float:
    return _first_float(
        row,
        "СуммаНДС",
        "СуммаНДСДокумента",
        "НДС",
        "VAT",
        "СуммаНалога",
        "СуммаНалогов",
        "TaxAmount",
    )


class OData1CClient:
    """1C OData (standard.odata) with HTTP Basic Auth."""

    DEFAULT_COUNTERPARTY_ENTITIES = (
        "Catalog_Контрагенты",
        "Catalog_Контрагенты_Контрагенты",
        "Catalog_Counterparties",
        "Catalog_ДоговорыКонтрагентов",
    )
    DEFAULT_INVOICE_ENTITIES = (
        "Document_СчетНаОплатуПокупателю",
        "Document_РеализацияТоваровУслуг",
        "Document_СчетФактураВыданный",
        "AccumulationRegister_ОплатаСчетов",
    )
    # Пробуем в первую очередь, если есть в $metadata
    PREFERRED_COUNTERPARTY_ENTITIES = (
        "Catalog_Контрагенты",
        "Catalog_ДоговорыКонтрагентов",
    )
    # Телефоны в типовой 1С лежат в регистре контактной информации (часто не публикуется в OData)
    CONTACT_INFO_ENTITY_CANDIDATES = (
        "InformationRegister_КонтактнаяИнформация",
        "InformationRegister_КонтактнаяИнформация_RecordType",
    )
    PREFERRED_INVOICE_ENTITIES = (
        "Document_СчетНаОплатуПокупателю",
        "Document_РеализацияТоваровУслуг",
        "Document_СчетНаОплатуПоставщика",
        "AccumulationRegister_ОплатаСчетов",
    )
    INVOICE_DOCUMENT_ENTITY = "Document_СчетНаОплатуПокупателю"
    CONTACT_KIND_ADDRESS = "b910ecef-9cc8-44e8-b0df-bc705acb83ed"
    CONTACT_KIND_PHONE = "c5bb357f-c3b0-48ba-8a12-a42cbf99a845"
    CONTACT_KIND_MOBILE = "f9e52726-2faf-4dca-85d0-559b80df2c53"
    CONTACT_INFO_ENTITY = "InformationRegister_КонтактнаяИнформация"
    COUNTERPARTY_OBJECT_TYPE = "StandardODATA.Catalog_Контрагенты"
    CONTACT_KIND_OBJECT_TYPE = "StandardODATA.Catalog_ВидыКонтактнойИнформации"
    PHONE_CONTACT_KINDS = (CONTACT_KIND_MOBILE, CONTACT_KIND_PHONE)
    INCOMING_PAYMENT_ENTITIES = (
        "Document_ПлатежноеПоручениеВходящее",
        "Document_ПриходныйКассовыйОрдер",
        "Document_ПоступлениеБезналичныхДенежныхСредств",
        "Document_ПоступлениеНаРасчетныйСчет",
    )
    MAX_ENTITIES_TO_PROBE = 12
    ODATA_PAGE_SIZE = 500
    DEFAULT_FETCH_LIMIT = 10000

    def __init__(
        self,
        base_url: str,
        basic_auth_user: str = "",
        basic_auth_password: str = "",
        api_user: str = None,
        api_password: str = None,
        timeout: int | tuple[int, int] = (10, 45),
        verify_ssl: bool = True,
        connect_retries: int = 2,
        counterparty_entities: Optional[List[str]] = None,
        invoice_entities: Optional[List[str]] = None,
    ):
        self._base_url = base_url.rstrip("/")
        user = api_user or basic_auth_user
        password = api_password or basic_auth_password
        if not user or not password:
            raise ValidationError("OData user and password are required")
        self._user = user
        self._password = password
        self._timeout = timeout if isinstance(timeout, tuple) else (10, int(timeout))
        self._connect_retries = max(0, int(connect_retries))
        self._verify_ssl = verify_ssl
        self._connected = False
        self.last_connect_error: Optional[str] = None
        self._access_token: Optional[str] = None
        self._sync_token: Optional[str] = None
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(user, password)
        self._session.verify = verify_ssl
        self._counterparty_entities = counterparty_entities
        self._invoice_entities = invoice_entities
        self._published_entities: Optional[List[str]] = None
        self.last_warning: Optional[str] = None
        self._counterparty_lookup: Optional[dict[str, dict]] = None
        self._contact_info_index: Optional[dict[str, dict]] = None
        self._connect_with_retries()

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token

    @property
    def sync_token(self) -> Optional[str]:
        return self._sync_token

    def _connect(self) -> None:
        url = self._base_url
        response = self._session.get(
            url,
            params={"$format": "json"},
            timeout=self._timeout,
        )
        if response.status_code == 401:
            raise AuthenticationError(
                "OData authentication failed (401). Check login and password.",
                status_code=401,
            )
        if response.status_code >= 400:
            raise APIError(
                f"OData connection failed: {response.status_code}",
                status_code=response.status_code,
            )
        self._access_token = "odata-basic"
        self._connected = True
        self.last_connect_error = None
        logger.debug(f" OData connected: {self._base_url} (user: {self._user})")

    def _connect_with_retries(self) -> None:
        last_error: Optional[Exception] = None
        attempts = 1 + self._connect_retries
        for attempt in range(attempts):
            try:
                self._connect()
                return
            except (requests.Timeout, requests.ConnectionError, APIError, AuthenticationError) as exc:
                last_error = exc
                self._connected = False
                self.last_connect_error = str(exc)
                if attempt < attempts - 1:
                    time.sleep(1.5 * (attempt + 1))
        if last_error:
            raise last_error

    def _ensure_connected(self) -> None:
        if self._connected and self._access_token:
            return
        self._connect_with_retries()

    def authenticate(self, user: str = None, password: str = None) -> AuthResponse:
        if user or password:
            self._session.auth = HTTPBasicAuth(
                user or self._user,
                password or self._password,
            )
        self._connect()
        return AuthResponse(token=self._access_token or "", expires="")

    def close(self) -> None:
        self._session.close()

    def _entity_url(self, entity: str) -> str:
        return f"{self._base_url}/{quote(entity, safe='')}"

    @staticmethod
    def _resolve_downloads_path(invoice_id: str) -> Path:
        cwd = Path.cwd()
        candidates = [
            cwd / "downloads",
            cwd / "backend" / "downloads",
            Path(__file__).resolve().parent.parent.parent / "downloads",
            Path(__file__).resolve().parent.parent / "downloads",
        ]
        safe_id = safe_filename_component(invoice_id)
        for downloads in candidates:
            try:
                downloads.mkdir(parents=True, exist_ok=True)
                return downloads / f"invoice_{safe_id}.pdf"
            except OSError:
                continue
        fallback = cwd / "downloads"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / f"invoice_{safe_id}.pdf"

    @staticmethod
    def _is_tabular_or_register_part(entity: str) -> bool:
        """Табличные части и RecordType не читаем как списки документов/справочников."""
        if entity.endswith("_RecordType"):
            return True
        if entity.startswith(("InformationRegister_", "AccumulationRegister_")):
            # Регистры — только явно разрешённые (например ОплатаСчетов)
            allowed_registers = ("AccumulationRegister_ОплатаСчетов",)
            return entity not in allowed_registers
        # Document_СчетНаОплатуПокупателю_Товары — табличная часть
        if entity.startswith("Document_") and entity.count("_") >= 2:
            return True
        if entity.startswith("Catalog_") and entity.count("_") >= 2:
            return True
        return False

    def _get_json(
        self,
        entity: str,
        params: dict,
        *,
        raise_on_auth: bool = False,
    ) -> Optional[dict]:
        self._ensure_connected()
        response = self._session.get(
            self._entity_url(entity),
            params=params,
            timeout=self._timeout,
        )
        if response.status_code == 404:
            return None
        if response.status_code == 401:
            logger.debug(f" OData {entity}: HTTP 401 (пропуск)")
            if raise_on_auth:
                raise AuthenticationError("OData authentication failed", status_code=401)
            return None
        if response.status_code >= 400:
            logger.debug(f" OData {entity}: HTTP {response.status_code}")
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _fetch_entity_rows(
        self,
        entity: str,
        base_params: dict,
        *,
        try_date_filter: bool = False,
        since_iso: Optional[str] = None,
        max_rows: Optional[int] = None,
    ) -> List[dict]:
        """Без $filter в OData (1С часто падает на Date) — фильтр по дате снаружи."""
        cap = max_rows if max_rows is not None else self.DEFAULT_FETCH_LIMIT
        params = dict(base_params)
        return self._fetch_entity_rows_paginated(entity, params, cap)

    def _fetch_entity_rows_paginated(
        self,
        entity: str,
        params: dict,
        max_rows: int,
    ) -> List[dict]:
        """Читает все страницы OData ($top + $skip), пока 1С отдаёт данные."""
        all_rows: List[dict] = []
        skip = 0
        page_size = min(self.ODATA_PAGE_SIZE, max_rows)
        while len(all_rows) < max_rows:
            page_params = dict(params)
            page_params["$top"] = page_size
            page_params["$skip"] = skip
            payload = self._get_json(entity, page_params)
            if payload is None:
                break
            rows = self._odata_rows(payload)
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < page_size:
                break
            skip += page_size
        if len(all_rows) > max_rows:
            all_rows = all_rows[:max_rows]
        if all_rows:
            logger.debug(f" OData: loaded {len(all_rows)} rows from {entity} (paginated)")
        return all_rows

    def _discover_entity_sets(self) -> List[str]:
        if self._published_entities is not None:
            return self._published_entities
        try:
            response = self._session.get(
                f"{self._base_url}/$metadata",
                timeout=self._timeout,
            )
            if response.status_code == 200:
                names = re.findall(r'EntitySet Name="([^"]+)"', response.text)
                self._published_entities = names
                if names:
                    self.last_warning = None
                    logger.debug(f" OData EntitySets from $metadata: {', '.join(names[:20])}")
                else:
                    self.last_warning = (
                        "В 1С не опубликованы объекты OData ($metadata пустой). "
                        "Попросите администратора 1С включить публикацию справочников "
                        "(Контрагенты) и документов (счета на оплату) в стандартном интерфейсе OData."
                    )
                    logger.debug(f" OData: {self.last_warning}")
                return names
        except Exception as e:
            logger.debug(f" OData: failed to read $metadata: {e}")
        self._published_entities = []
        return []

    def _score_invoice_entity(self, name: str) -> int:
        lower = name.lower()
        if name in self.PREFERRED_INVOICE_ENTITIES:
            return 100
        if name == "Document_СчетНаОплатуПокупателю":
            return 95
        if "счетнаоплатупокупателю" in lower.replace("_", ""):
            return 90
        if name == "Document_РеализацияТоваровУслуг":
            return 85
        if "реализациятоваров" in lower:
            return 80
        if "оплатасчетов" in lower.replace("_", ""):
            return 70
        if name.startswith("Document_") and "счет" in lower and "фактур" not in lower:
            return 50
        return 0

    def _score_counterparty_entity(self, name: str) -> int:
        if name in self.PREFERRED_COUNTERPARTY_ENTITIES:
            return 100
        if name == "Catalog_Контрагенты":
            return 95
        lower = name.lower()
        if name.startswith("Catalog_") and "контрагент" in lower and name.count("_") == 1:
            return 80
        if "договорыконтрагентов" in lower.replace("_", ""):
            return 60
        return 0

    def _entities_to_try(
        self,
        configured: Optional[List[str]],
        defaults: tuple,
        kind: str,
    ) -> List[str]:
        if configured:
            return list(configured)
        discovered = self._discover_entity_sets()
        preferred = (
            self.PREFERRED_COUNTERPARTY_ENTITIES
            if kind == "counterparty"
            else self.PREFERRED_INVOICE_ENTITIES
        )
        result: List[str] = []
        seen = set()

        def add(name: str) -> None:
            if name and name not in seen and not self._is_tabular_or_register_part(name):
                seen.add(name)
                result.append(name)

        for name in preferred:
            if not discovered or name in discovered:
                add(name)

        if discovered:
            scored = []
            for e in discovered:
                if self._is_tabular_or_register_part(e):
                    continue
                score = (
                    self._score_counterparty_entity(e)
                    if kind == "counterparty"
                    else self._score_invoice_entity(e)
                )
                if score > 0:
                    scored.append((score, e))
            scored.sort(key=lambda x: (-x[0], x[1]))
            for _, e in scored:
                add(e)

        for name in defaults:
            add(name)

        if not result:
            return list(defaults)
        return result[: self.MAX_ENTITIES_TO_PROBE]

    def _odata_rows(self, payload: dict) -> List[dict]:
        if not payload:
            return []
        return payload.get("value") or []

    def _row_to_counterparty(self, row: dict) -> Counterparty:
        ref = _first_str(row, "Ref_Key", "Ref", "Key", "id")
        return Counterparty.from_dict(
            {
                "id": ref,
                "fullName": _first_str(
                    row,
                    "НаименованиеПолное",
                    "Description",
                    "Наименование",
                    "FullName",
                ),
                "shortName": _first_str(row, "Code", "Код"),
                "bin": _first_str(
                    row,
                    "ИНН",
                    "ИдентификационныйКодЛичности",
                    "BIN",
                    "IdentificationNumber",
                ),
                "rnn": _first_str(row, "РНН", "rnn"),
                "kbe": _first_str(row, "КБЕ", "kbe"),
                "address": _first_str(row, "ЮридическийАдрес", "Адрес", "Address"),
                "phone": _first_str(row, "Телефон", "Phone", "НомерТелефона"),
                "email": _first_str(row, "Email", "АдресЭП"),
            }
        )

    def _row_to_invoice(self, row: dict) -> Invoice:
        ref = _first_str(row, "Ref_Key", "Ref", "Key", "id")
        cp_key = _first_str(
            row,
            "Контрагент_Key",
            "Counterparty_Key",
            "Покупатель_Key",
            "Заказчик_Key",
            "Плательщик_Key",
            "Грузополучатель_Key",
        )
        cp_name = _first_str(
            row,
            "Контрагент_Description",
            "Counterparty_Description",
            "КонтрагентНаименование",
            "Контрагент",
        )
        if cp_key and not _looks_like_guid(cp_key):
            if not cp_name or _looks_like_guid(cp_name):
                cp_name = cp_key
            cp_key = _first_str(
                row,
                "Контрагент_Key",
                "Counterparty_Key",
                "Покупатель_Key",
            ) or cp_key
        if _looks_like_guid(cp_name):
            cp_name = ""
        date_val = _first_str(row, "Date", "Дата", "date")
        if "T" in date_val:
            date_val = date_val.split("T")[0]
        amount = _first_float(
            row,
            "СуммаДокумента",
            "Amount",
            "Сумма",
            "amount",
            "СуммаОплаты",
        )
        paid_amount = _first_float(
            row,
            "СуммаОплачена",
            "Оплачено",
            "PaidAmount",
            "ОплаченнаяСумма",
        )
        payment_status_raw = _first_str(
            row,
            "СтатусОплаты",
            "PaymentStatus",
            "СостояниеОплаты",
            "Оплачен",
            "Paid",
        ).strip()
        payment_status = ""
        low = payment_status_raw.lower()
        if low in ("paid", "оплачен", "оплачено", "true", "истина"):
            payment_status = "paid"
        elif low in ("overdue", "просрочен", "просрочено"):
            payment_status = "overdue"
        elif low:
            payment_status = "unpaid"
        return Invoice.from_dict(
            {
                "id": ref,
                "number": _first_str(row, "Number", "Номер", "number"),
                "date": date_val,
                "counterparty_id": cp_key,
                "counterparty_name": cp_name,
                "amount": amount,
                "currency": _first_str(row, "Валюта", "ВалютаДокумента_Key", "Currency") or "KZT",
                "status": (
                    "posted"
                    if row.get("Posted") is True
                    else (
                        "draft"
                        if row.get("Posted") is False
                        else _first_str(row, "Posted", "Проведен") or "draft"
                    )
                ),
                "paid_amount": paid_amount,
                "payment_status": payment_status,
            }
        )

    @staticmethod
    def _parse_date_value(date_str: str) -> Optional[date]:
        if not date_str:
            return None
        raw = str(date_str).split("T")[0].strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _calculate_due_date(invoice_date: date, due_day: int = 5) -> date:
        safe_day = max(1, min(31, int(due_day or 5)))
        if invoice_date.month == 12:
            year, month = invoice_date.year + 1, 1
        else:
            year, month = invoice_date.year, invoice_date.month + 1
        max_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(safe_day, max_day))

    def _load_payments_by_invoice_id(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> dict[str, list]:
        """Платежи из 1С, привязанные к счёту на оплату (ДокументОснование)."""
        payments: dict[str, list] = {}
        since_day = str(since).split("T")[0] if since else None
        until_day = str(until).split("T")[0] if until else None
        discovered = self._discover_entity_sets()
        for entity in self.INCOMING_PAYMENT_ENTITIES:
            if discovered and entity not in discovered:
                continue
            rows = self._fetch_entity_rows(
                entity,
                {"$format": "json"},
                max_rows=self.DEFAULT_FETCH_LIMIT,
            )
            for row in rows:
                posted_raw = row.get("Posted")
                posted_text = _first_str(row, "Posted", "Проведен").strip().lower()
                if not (
                    posted_raw is True
                    or posted_text in ("true", "истина", "проведен", "проведён", "posted")
                ):
                    continue

                invoice_id = _extract_guid_key(
                    _first_str(
                        row,
                        "ДокументОснование_Key",
                        "ДокументОснование",
                        "Основание_Key",
                        "Основание",
                        "СчетНаОплатуПокупателю_Key",
                        "СчетНаОплату_Key",
                        "Invoice_Key",
                    )
                )
                base_type = _first_str(row, "ДокументОснование_Type")
                if not invoice_id:
                    continue

                if base_type and "СчетНаОплатуПокупателю" not in base_type:
                    continue
                key = invoice_id.strip().lower()
                pay_date = _first_str(
                    row,
                    "ДатаВыписки",
                    "Date",
                    "ДатаВходящегоДокумента",
                )
                if since_day or until_day:
                    parsed_pay = self._parse_date_value(pay_date or "")
                    if parsed_pay:
                        pay_day = parsed_pay.isoformat()
                        if since_day and pay_day < since_day:
                            continue
                        if until_day and pay_day > until_day:
                            continue
                amount = _first_float(row, "СуммаДокумента", "Amount", "Сумма")
                payments.setdefault(key, []).append(
                    {"amount": amount or 0.0, "date": pay_date}
                )
        if payments:
            logger.debug(f" OData: payments linked to {len(payments)} invoices")
        return payments

    @staticmethod
    def _invoice_due_dates(
        invoice_date: date,
        rent_due_day: int,
        utilities_due_day: int,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> tuple[date, date, date]:
        """Сроки в месяце выбранного периода (аренда, коммуналка, эксплуатация).

        Корректно только когда счёт датирован заранее (аренда за июль часто
        датируется концом июня) — период нередко совпадает с месяцем самого
        счёта (счёт от 20.08 в периоде "2026-08"), и тогда "5-е число
        периода" оказывается РАНЬШЕ даты счёта. Такой срок недействителен —
        переносим на следующий месяц после даты счёта.
        """
        ops_day = operations_due_day if operations_due_day is not None else rent_due_day
        if period and len(period) == 7 and period[4] == "-":
            try:
                year, month = int(period[:4]), int(period[5:7])
                last = calendar.monthrange(year, month)[1]
                rent = date(year, month, min(max(1, rent_due_day), last))
                util = date(year, month, min(max(1, utilities_due_day), last))
                ops = date(year, month, min(max(1, ops_day), last))
                if rent <= invoice_date:
                    rent = OData1CClient._calculate_due_date(invoice_date, rent_due_day)
                if util <= invoice_date:
                    util = OData1CClient._calculate_due_date(invoice_date, utilities_due_day)
                if ops <= invoice_date:
                    ops = OData1CClient._calculate_due_date(invoice_date, ops_day)
                return rent, util, ops
            except ValueError:
                pass
        return (
            OData1CClient._calculate_due_date(invoice_date, rent_due_day),
            OData1CClient._calculate_due_date(invoice_date, utilities_due_day),
            OData1CClient._calculate_due_date(invoice_date, ops_day),
        )

    def _resolve_payment_status(
        self,
        invoice_amount: float,
        invoice_date_str: str,
        payments: list,
        due_day: int = 5,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
        invoice_items: Optional[list] = None,
    ) -> tuple[str, Optional[str], float]:
        total_paid = sum(float(p.get("amount") or 0) for p in payments)
        paid_dates = [
            self._parse_date_value(p.get("date") or "")
            for p in payments
            if p.get("date")
        ]
        paid_dates = [d for d in paid_dates if d]
        paid_at = max(paid_dates).isoformat() if paid_dates else None

        amount = float(invoice_amount or 0)
        if paid_enough(amount, total_paid):
            return "paid", paid_at, total_paid

        inv_date = self._parse_date_value(invoice_date_str)
        if inv_date:
            util_day = utilities_due_day if utilities_due_day is not None else due_day
            ops_day = operations_due_day if operations_due_day is not None else due_day
            rent_due, util_due, ops_due = self._invoice_due_dates(
                inv_date, due_day, util_day, ops_day, period
            )
            today = date.today()
            service_types = resolve_invoice_service_types(invoice_items or [])
            if len(service_types) == 1:
                st = service_types[0]
                applicable = due_date_in_invoice_month(
                    inv_date,
                    due_day_for_service_type(
                        st,
                        rent=due_day,
                        utilities=util_day,
                        operations=ops_day,
                    ),
                )
                if today > applicable:
                    return "overdue", paid_at, total_paid
            elif today > util_due or today > rent_due or today > ops_due:
                return "overdue", paid_at, total_paid

        # Не просрочен, но что-то уже поступило — "partial", не "unpaid".
        # Просрочка (выше) важнее: частично оплаченный, но просроченный счёт
        # остаётся overdue, а не превращается в partial.
        if total_paid > 0:
            return "partial", paid_at, total_paid
        return "unpaid", paid_at, total_paid

    def _enrich_invoices_payment_status(
        self,
        invoices: List[Invoice],
        due_day: int = 5,
        payment_since: Optional[str] = None,
        payment_until: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> List[Invoice]:
        if not invoices:
            return invoices
        payments_map = self._load_payments_by_invoice_id(
            since=payment_since,
            until=payment_until,
        )
        paid_count = 0
        for inv in invoices:
            inv_key = (inv.id or "").strip().lower()
            linked = payments_map.get(inv_key, [])
            # Явный СтатусОплаты из 1С — не пересчитывать unpaid-overdue по due_date.
            explicit = str(inv.payment_status or "").lower().strip()
            if explicit in ("paid", "unpaid", "overdue"):
                pay_status = explicit
                if linked:
                    total_paid = sum(float(p.get("amount") or 0) for p in linked)
                    paid_dates = [
                        self._parse_date_value(p.get("date") or "")
                        for p in linked
                        if p.get("date")
                    ]
                    paid_dates = [d for d in paid_dates if d]
                    paid_at = (
                        max(paid_dates).isoformat() if paid_dates else inv.paid_at
                    )
                else:
                    total_paid = float(inv.paid_amount or 0)
                    paid_at = inv.paid_at
                if pay_status == "paid" and total_paid <= 0:
                    total_paid = float(inv.paid_amount or inv.amount or 0)
            elif paid_enough(float(inv.amount or 0), float(inv.paid_amount or 0)):
                total_paid = float(inv.paid_amount or 0)
                paid_at = inv.paid_at
                pay_status = "paid"
            elif not linked and float(inv.paid_amount or 0) > 0:
                # Сумма оплаты уже известна из самого счёта — нет отдельных
                # связанных платёжных документов. Не теряем частичную оплату,
                # подставляя total_paid=0 через _resolve_payment_status([], ...).
                total_paid = float(inv.paid_amount or 0)
                paid_at = inv.paid_at
                due_status, _, _ = self._resolve_payment_status(
                    inv.amount,
                    inv.date,
                    [],
                    due_day,
                    utilities_due_day=utilities_due_day,
                    operations_due_day=operations_due_day,
                    period=period,
                    invoice_items=inv.items,
                )
                pay_status = "overdue" if due_status == "overdue" else "partial"
            else:
                pay_status, paid_at, total_paid = self._resolve_payment_status(
                    inv.amount,
                    inv.date,
                    linked,
                    due_day,
                    utilities_due_day=utilities_due_day,
                    operations_due_day=operations_due_day,
                    period=period,
                    invoice_items=inv.items,
                )
            inv.payment_status = pay_status
            inv.paid_at = paid_at
            inv.paid_amount = total_paid if total_paid > 0 else None
            inv_date = self._parse_date_value(inv.date)
            if inv_date:
                util_day = utilities_due_day if utilities_due_day is not None else due_day
                ops_day = operations_due_day if operations_due_day is not None else due_day
                service_types = resolve_invoice_service_types(inv.items or [])
                if len(service_types) == 1:
                    day = due_day_for_service_type(
                        service_types[0],
                        rent=due_day,
                        utilities=util_day,
                        operations=ops_day,
                    )
                    inv.due_date = due_date_in_invoice_month(inv_date, day).isoformat()
                else:
                    rent_due, _, _ = self._invoice_due_dates(
                        inv_date, due_day, util_day, ops_day, period
                    )
                    inv.due_date = rent_due.isoformat()
            if pay_status == "paid":
                paid_count += 1
        logger.debug(f" OData: payment status — paid {paid_count}, total invoices {len(invoices)}")
        return invoices

    @staticmethod
    def _invoice_belongs_to_period(
        invoice_date_str: Optional[str],
        due_date_str: Optional[str],
        period: Optional[str],
    ) -> bool:
        if not period or len(period) != 7 or period[4] != "-":
            return True
        if not invoice_date_str and not due_date_str:
            return False
        try:
            period_year, period_month = int(period[:4]), int(period[5:7])
        except ValueError:
            return True

        for date_str in (invoice_date_str, due_date_str):
            if not date_str:
                continue
            raw = str(date_str).split("T")[0]
            if raw.startswith(period):
                return True
            inv_date = OData1CClient._parse_date_value(raw)
            if not inv_date:
                continue
            if inv_date.year == period_year and inv_date.month == period_month:
                return True
            prev_month = period_month - 1
            prev_year = period_year
            if prev_month < 1:
                prev_month = 12
                prev_year -= 1
            if inv_date.year == prev_year and inv_date.month == prev_month:
                return True
        return False

    @staticmethod
    def _period_invoice_fetch_bounds(period: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """since/until для выборки счетов по периоду YYYY-MM (включая предыдущий месяц)."""
        if not period or len(period) != 7 or period[4] != "-":
            return None, None
        try:
            year = int(period[:4])
            month = int(period[5:7])
            if month < 1 or month > 12:
                return None, None
        except ValueError:
            return None, None
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        since = f"{prev_year}-{prev_month:02d}-01"
        last_day = calendar.monthrange(year, month)[1]
        until = f"{year}-{month:02d}-{last_day}"
        return since, until

    @staticmethod
    def _payment_until_with_grace(until: Optional[str], grace_days: int = 45) -> Optional[str]:
        """Платёж может прийти после даты счёта — расширяем окно для поиска оплат."""
        if not until:
            return None
        raw = str(until).split("T")[0]
        try:
            end = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return until
        return (end + timedelta(days=grace_days)).isoformat()

    def get_latest_invoice_status_by_counterparty(
        self,
        due_day: int = 5,
        period: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
    ) -> dict[str, dict]:
        """Последний счёт контрагента и статус оплаты из 1С (опционально за период YYYY-MM)."""
        since, until = self._period_invoice_fetch_bounds(period)
        payment_until = self._payment_until_with_grace(until)
        util_day = utilities_due_day if utilities_due_day is not None else due_day
        ops_day = operations_due_day if operations_due_day is not None else due_day
        invoices = self.get_invoices(
            since=since,
            until=until,
            limit=self.DEFAULT_FETCH_LIMIT,
            due_day=due_day,
            enrich_payment_status=True,
            payment_since=since,
            payment_until=payment_until,
            utilities_due_day=util_day,
            operations_due_day=ops_day,
            period=period,
        )
        latest: dict[str, Invoice] = {}
        for inv in invoices:
            cp_key = (inv.counterparty_id or "").strip().lower()
            if not cp_key:
                continue
            if period and not self._invoice_belongs_to_period(inv.date, inv.due_date, period):
                continue
            prev = latest.get(cp_key)
            if not prev or (inv.date or "") > (prev.date or ""):
                latest[cp_key] = inv

        result: dict[str, dict] = {}
        for cp_key, inv in latest.items():
            doc_status = (
                "posted"
                if str(inv.status).lower() in ("posted", "true", "проведен")
                else "draft"
            )
            pay_status = str(inv.payment_status or "unpaid").lower()
            result[cp_key] = {
                "invoiceId": inv.id,
                "invoiceNumber": inv.number,
                "invoiceDate": inv.date,
                "dueDate": inv.due_date,
                "documentStatus": doc_status,
                "paymentStatus": pay_status,
                "paidAt": inv.paid_at,
                "amount": inv.amount,
                "paidAmount": inv.paid_amount,
            }
        return result

    def get_invoice_counts_by_counterparty(self) -> dict[str, int]:
        """Количество счетов на оплату по каждому контрагенту (Ref_Key)."""
        counts: dict[str, int] = {}
        invoices = self.get_invoices(
            limit=self.DEFAULT_FETCH_LIMIT,
            enrich_payment_status=False,
        )
        for inv in invoices:
            cp_key = _extract_guid_key(inv.counterparty_id or "")
            if not cp_key:
                continue
            counts[cp_key] = counts.get(cp_key, 0) + 1
        if counts:
            logger.debug(f" OData: invoice counts for {len(counts)} counterparties")
        return counts

    def get_contracts_by_counterparty(self) -> dict[str, list[dict]]:
        """Договоры из Catalog_ДоговорыКонтрагентов, сгруппированные по контрагенту."""
        result: dict[str, list[dict]] = {}
        entity = "Catalog_ДоговорыКонтрагентов"
        discovered = self._discover_entity_sets()
        if discovered and entity not in discovered:
            return result
        rows = self._fetch_entity_rows(
            entity,
            {"$format": "json"},
            max_rows=self.DEFAULT_FETCH_LIMIT,
        )
        for row in rows:
            if row.get("DeletionMark") or row.get("IsFolder"):
                continue
            owner = _contact_owner_key(row)
            if not owner:
                owner = _extract_guid_key(
                    _first_str(row, "Владелец_Key", "Owner_Key", "Контрагент_Key")
                )
            if not owner:
                continue
            ref = _first_str(row, "Ref_Key", "Ref", "Key", "id")
            date_raw = _first_str(row, "ДатаДоговора", "Date")
            if "T" in date_raw:
                date_raw = date_raw.split("T")[0]
            contract = {
                "id": ref,
                "number": _first_str(row, "НомерДоговора", "Number", "Code"),
                "date": date_raw,
                "type": _first_str(row, "ВидДоговора", "Type"),
                "name": _first_str(row, "Description", "Наименование"),
            }
            result.setdefault(owner, []).append(contract)
        if result:
            logger.debug(f" OData: contracts loaded for {len(result)} counterparties")
        return result

    def _load_phones_by_counterparty_ref(self) -> dict:
        """Телефоны из регистра контактной информации (если опубликован в OData)."""
        phones: dict = {}
        discovered = self._discover_entity_sets()
        entities = [e for e in self.CONTACT_INFO_ENTITY_CANDIDATES if e in discovered]
        if not entities:
            return phones
        params = {"$format": "json", "$top": 1000}
        for entity in entities:
            rows = self._fetch_entity_rows(entity, params)
            for row in rows:
                phone = _extract_phone_from_row(row)
                if not phone:
                    continue
                owner = _first_str(
                    row,
                    "Объект",
                    "Контрагент_Key",
                    "Владелец_Key",
                    "ОбъектВладелец",
                )
                owner_type = _first_str(row, "Объект_Type", "Владелец_Type")
                if owner and "Контрагент" not in owner_type:
                    continue
                if owner:
                    phones[_extract_guid_key(owner)] = phone
        if phones:
            logger.debug(f" OData: loaded {len(phones)} phones from contact information register")
        return phones

    def _enrich_counterparties(self, items: List[Counterparty]) -> List[Counterparty]:
        if not items:
            return items
        phones_by_ref = self._load_phones_by_counterparty_ref()
        contact_names: dict = {}
        if "Catalog_КонтактныеЛица" in self._discover_entity_sets():
            rows = self._fetch_entity_rows(
                "Catalog_КонтактныеЛица",
                {"$format": "json"},
                max_rows=self.DEFAULT_FETCH_LIMIT,
            )
            for row in rows:
                if row.get("DeletionMark"):
                    continue
                owner = _first_str(row, "ОбъектВладелец")
                owner_type = _first_str(row, "ОбъектВладелец_Type")
                if owner and "Контрагент" in owner_type:
                    name = _first_str(row, "Description", "Фамилия", "Имя")
                    if name:
                        contact_names[owner.lower()] = name
            if contact_names:
                logger.debug(f" OData: {len(contact_names)} contact persons linked to counterparties")

        contact_index = self._load_contact_info_index()
        enriched = 0
        for cp in items:
            cp_key = _extract_guid_key(cp.id or "")
            if not (cp.phone or cp.phone_number) and cp_key in phones_by_ref:
                cp.phone = phones_by_ref[cp_key]
                cp.phone_number = phones_by_ref[cp_key]
                enriched += 1
            if not cp.address and cp_key in contact_index:
                cp.address = contact_index[cp_key].get("address", "") or cp.address
            ck = contact_names.get(cp_key, "")
            if ck:
                cp.short_name = cp.short_name or ck
        if enriched:
            logger.debug(f" OData: phones attached for {enriched} counterparties")
        return items

    def get_counterparties(self, limit: int = 10000) -> List[Counterparty]:
        """Только справочник Catalog_Контрагенты — как в 1С, без подмены другими сущностями."""
        fetch_limit = min(limit or self.DEFAULT_FETCH_LIMIT, self.DEFAULT_FETCH_LIMIT)
        params = {"$format": "json"}
        entity = "Catalog_Контрагенты"
        if self._counterparty_entities:
            entity = self._counterparty_entities[0]
        discovered = self._discover_entity_sets()
        if discovered and entity not in discovered:
            self.last_warning = (
                f"В OData нет сущности {entity}. "
                "Попросите 1С опубликовать справочник «Контрагенты»."
            )
            logger.debug(f" OData: {self.last_warning}")
            return []

        rows = self._fetch_entity_rows(entity, params, max_rows=fetch_limit)
        if not rows:
            self.last_warning = (
                "Справочник контрагентов в 1С пуст или недоступен по OData."
            )
            logger.debug(f" OData: {self.last_warning}")
            return []

        items: List[Counterparty] = []
        skipped_folder = 0
        skipped_deleted = 0
        folder_names: dict[str, str] = {}
        for row in rows:
            if row.get("DeletionMark"):
                skipped_deleted += 1
                continue
            if row.get("IsFolder"):
                skipped_folder += 1
                ref = _first_str(row, "Ref_Key", "Ref", "Key", "id").lower()
                name = _first_str(
                    row,
                    "НаименованиеПолное",
                    "Description",
                    "Наименование",
                    "FullName",
                )
                if ref and name:
                    folder_names[ref] = name
                continue
            cp = self._row_to_counterparty(row)
            if not (cp.full_name or cp.short_name or "").strip():
                continue
            parent = _first_str(row, "Parent_Key", "Parent", "Родитель_Key", "Родитель")
            if parent and parent.lower().replace("-", "").strip("0"):
                cp.parent = parent
                cp.folder_name = folder_names.get(parent.lower(), "") or _first_str(
                    row, "Parent_Description", "Родитель_Description"
                )
            items.append(cp)

        # Second pass: folder names may appear after children in OData page order.
        if folder_names:
            for cp in items:
                if cp.parent and not cp.folder_name:
                    cp.folder_name = folder_names.get(cp.parent.lower(), "")

        logger.debug(
            f" OData: {len(items)} counterparties from {entity} "
            f"(raw {len(rows)}, folders {skipped_folder}, deleted {skipped_deleted})"
        )
        return self._enrich_counterparties(items)

    def _load_counterparty_lookup(self) -> dict[str, dict]:
        """Ref_Key → {name, bin} из Catalog_Контрагенты."""
        lookup: dict[str, dict] = {}
        entity = "Catalog_Контрагенты"
        if self._counterparty_entities:
            entity = self._counterparty_entities[0]
        discovered = self._discover_entity_sets()
        if discovered and entity not in discovered:
            return lookup
        rows = self._fetch_entity_rows(
            entity,
            {"$format": "json"},
            max_rows=self.DEFAULT_FETCH_LIMIT,
        )
        for row in rows:
            if row.get("DeletionMark") or row.get("IsFolder"):
                continue
            ref = _first_str(row, "Ref_Key", "Ref", "Key", "id").lower()
            if not ref:
                continue
            name = _first_str(
                row,
                "НаименованиеПолное",
                "Description",
                "Наименование",
                "FullName",
            )
            if not name:
                continue
            lookup[ref] = {
                "name": name,
                "bin": _first_str(
                    row,
                    "ИНН",
                    "ИдентификационныйКодЛичности",
                    "BIN",
                ),
            }
        if lookup:
            logger.debug(f" OData: counterparty lookup for invoices: {len(lookup)} names")
        return lookup

    def _get_counterparty_lookup(self) -> dict[str, dict]:
        if self._counterparty_lookup is None:
            self._counterparty_lookup = self._load_counterparty_lookup()
        return self._counterparty_lookup

    def _enrich_invoices(self, invoices: List[Invoice]) -> List[Invoice]:
        if not invoices:
            return invoices
        lookup = self._get_counterparty_lookup()
        enriched = 0
        for inv in invoices:
            cp_key = (inv.counterparty_id or "").strip().lower()
            if not cp_key or cp_key == "00000000-0000-0000-0000-000000000000":
                continue
            info = lookup.get(cp_key)
            if not info and hasattr(self, "_fetch_counterparty_name"):
                name = self._fetch_counterparty_name(inv.counterparty_id)
                if name:
                    info = {"name": name, "bin": ""}
            if not info:
                continue
            if not (inv.counterparty_name or "").strip():
                inv.counterparty_name = info["name"]
                enriched += 1
            if not inv.counterparty:
                inv.counterparty = {
                    "id": inv.counterparty_id,
                    "name": inv.counterparty_name or info["name"],
                    "bin": info.get("bin") or "",
                }
            elif not inv.counterparty.get("name"):
                inv.counterparty["name"] = info["name"]
                if info.get("bin"):
                    inv.counterparty["bin"] = info["bin"]
        if enriched:
            logger.debug(f" OData: filled counterparty names on {enriched} invoices")
        missing = sum(
            1
            for inv in invoices
            if (inv.counterparty_id or "").strip()
            and not (inv.counterparty_name or "").strip()
        )
        if missing:
            logger.debug(f" OData: {missing} invoices still without counterparty name")
        return invoices

    def get_invoices(
        self,
        since: Union[str, datetime] = None,
        until: Union[str, datetime] = None,
        limit: int = 10000,
        due_day: int = 5,
        enrich_payment_status: bool = True,
        payment_since: Optional[str] = None,
        payment_until: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> List[Invoice]:
        entities = self._entities_to_try(
            self._invoice_entities,
            self.DEFAULT_INVOICE_ENTITIES,
            "invoice",
        )
        fetch_limit = min(limit or self.DEFAULT_FETCH_LIMIT, self.DEFAULT_FETCH_LIMIT)
        params = {"$format": "json"}
        since_iso = None
        if since:
            if isinstance(since, datetime):
                since_iso = since.strftime("%Y-%m-%dT00:00:00")
            else:
                since_iso = str(since).split("T")[0] + "T00:00:00"
        until_iso = None
        if until:
            if isinstance(until, datetime):
                until_iso = until.strftime("%Y-%m-%dT23:59:59")
            else:
                until_iso = str(until).split("T")[0] + "T23:59:59"
        for entity in entities:
            rows = self._fetch_entity_rows(
                entity,
                params,
                try_date_filter=bool(since_iso),
                since_iso=since_iso,
                max_rows=fetch_limit,
            )
            if (since_iso or until_iso) and rows:
                filtered = []
                since_day = since_iso.split("T")[0] if since_iso else None
                until_day = until_iso.split("T")[0] if until_iso else None
                for row in rows:
                    date_val = _first_str(row, "Date", "Дата", "date")
                    if not date_val:
                        filtered.append(row)
                        continue
                    try:
                        row_date = date_val.split("T")[0]
                        if since_day and row_date < since_day:
                            continue
                        if until_day and row_date > until_day:
                            continue
                        filtered.append(row)
                    except Exception:
                        filtered.append(row)
                rows = filtered
            if rows:
                logger.debug(f" OData: {len(rows)} invoices from {entity}")
                items = [self._row_to_invoice(r) for r in rows]
                items = self._enrich_invoices(items)
                if enrich_payment_status:
                    pay_since = payment_since
                    if pay_since is None and since_iso:
                        pay_since = since_iso.split("T")[0]
                    pay_until = payment_until
                    if pay_until is None and until_iso:
                        pay_until = self._payment_until_with_grace(until_iso.split("T")[0])
                    return self._enrich_invoices_payment_status(
                        items,
                        due_day=due_day,
                        payment_since=pay_since,
                        payment_until=pay_until,
                        utilities_due_day=utilities_due_day,
                        operations_due_day=operations_due_day,
                        period=period,
                    )
                util_day = utilities_due_day if utilities_due_day is not None else due_day
                ops_day = operations_due_day if operations_due_day is not None else due_day
                for inv in items:
                    inv_date = self._parse_date_value(inv.date)
                    if inv_date:
                        rent_due, _, _ = self._invoice_due_dates(
                            inv_date, due_day, util_day, ops_day, period
                        )
                        inv.due_date = rent_due.isoformat()
                return items
        if not self.last_warning:
            self.last_warning = (
                "Счета не найдены: в OData нет подходящих документов. "
                "Уточните имя сущности у администратора 1С или задайте ONE_C_ODATA_INVOICE_ENTITIES."
            )
        logger.debug(f" OData: {self.last_warning}")
        return []

    def get_payments(
        self,
        since: Union[str, datetime] = None,
        limit: int = None,
    ) -> List[Payment]:
        return []

    def get_balance(
        self,
        counterparty_id: str,
        since: Union[str, datetime] = None,
    ) -> Balance:
        return Balance.from_dict(
            {
                "counterparty": {"id": counterparty_id, "name": ""},
                "balance": {"receivable": 0.0, "payable": 0.0, "net": 0.0},
                "aging": [],
            }
        )

    def get_data(self, limit: int = 100) -> DataResponse:
        return DataResponse(data=[], has_more=False, sync_token="")

    def get_all_data(self, batch_size: int = 100) -> List[dict]:
        return []

    def confirm(self, *args, **kwargs) -> ConfirmResponse:
        raise ValidationError("confirm is not supported for OData")

    def _fetch_counterparty_name(self, counterparty_key: str) -> str:
        if not counterparty_key or counterparty_key == "00000000-0000-0000-0000-000000000000":
            return ""
        payload = self._get_json(
            f"Catalog_Контрагенты(guid'{counterparty_key}')",
            {"$format": "json"},
        )
        if not payload:
            return ""
        return _first_str(
            payload,
            "НаименованиеПолное",
            "Description",
            "Наименование",
        )

    def _fetch_invoice_tabular_lines(self, invoice_id: str, part: str) -> List[dict]:
        response = self._session.get(
            f"{self._base_url}/{quote(self.INVOICE_DOCUMENT_ENTITY, safe='')}(guid'{invoice_id}')/{part}",
            params={"$format": "json"},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            return []
        try:
            return response.json().get("value") or []
        except ValueError:
            return []

    def fetch_invoice_line_items(self, invoice_id: str) -> List[dict]:
        """Строки счёта (Услуги/Товары) — для классификации аренда/коммуналка."""
        try:
            invoice_id = _guid_literal(invoice_id, "invoice_id")
        except ValidationError:
            return []
        items: List[dict] = []
        for part, name_keys in (
            ("Услуги", ("Содержание", "Номенклатура_Description", "Description")),
            ("Товары", ("Номенклатура_Description", "Содержание", "Description")),
        ):
            for row in self._fetch_invoice_tabular_lines(invoice_id, part):
                name = _first_str(row, *name_keys)
                if name:
                    items.append({"name": name})
        return items

    def _load_contact_info_index(self) -> dict[str, dict]:
        if self._contact_info_index is not None:
            return self._contact_info_index
        index: dict[str, dict] = {}
        discovered = self._discover_entity_sets()
        entities = [e for e in self.CONTACT_INFO_ENTITY_CANDIDATES if e in discovered]
        if not entities:
            self._contact_info_index = index
            return index
        for entity in entities:
            rows = self._fetch_entity_rows(
                entity,
                {"$format": "json"},
                max_rows=self.DEFAULT_FETCH_LIMIT,
            )
            for row in rows:
                owner = _contact_owner_key(row)
                if not owner:
                    continue
                owner_type = _first_str(
                    row, "Объект_Type", "Владелец_Type", "ОбъектВладелец_Type"
                ).lower()
                if owner_type and not any(
                    token in owner_type
                    for token in ("контрагент", "организац", "физическ", "физлиц")
                ):
                    continue
                kind = _contact_kind_key(row)
                value = _first_str(row, "Представление", "Значение", "ТекстоваяСтрока")
                if not value:
                    continue
                slot = index.setdefault(owner, {})
                contact_type = _first_str(row, "Тип", "Type").lower()
                is_address = (
                    kind == self.CONTACT_KIND_ADDRESS.lower()
                    or contact_type == "адрес"
                    or _looks_like_address(value)
                )
                if is_address:
                    default = row.get("ЗначениеПоУмолчанию") is True
                    if default or not slot.get("address"):
                        slot["address"] = value
                elif kind == self.CONTACT_KIND_PHONE.lower() or _normalize_phone(value):
                    display = _contact_phone_display(value)
                    if not display:
                        continue
                    phones: list = slot.setdefault("phones", [])
                    seen = {_phone_dedup_key(p) for p in phones}
                    key = _phone_dedup_key(value)
                    if key and key in seen:
                        continue
                    phones.append(display)
                    if not slot.get("phone"):
                        slot["phone"] = display
        self._contact_info_index = index
        if index:
            logger.debug(" OData: contact info index for %s owners", len(index))
        return index

    def _load_bank_account_details(self, account_key: str) -> dict:
        empty = {
            "iik": "",
            "bank_name": "",
            "bank_bik": "",
            "currency": "KZT",
        }
        if not account_key or account_key == "00000000-0000-0000-0000-000000000000":
            return empty
        acc = self._get_json(
            f"Catalog_БанковскиеСчета(guid'{account_key}')",
            {"$format": "json"},
        )
        if not acc:
            return empty
        iik = _first_str(acc, "НомерСчета", "Description")
        bank_key = _first_str(acc, "Банк_Key")
        bank_name = ""
        bank_bik = ""
        if bank_key:
            bank = self._get_json(
                f"Catalog_Банки(guid'{bank_key}')",
                {"$format": "json"},
            )
            if bank:
                bank_name = _first_str(bank, "Description", "Наименование")
                bank_bik = _first_str(bank, "БИК", "Код")
        return {
            "iik": iik,
            "bank_name": bank_name,
            "bank_bik": bank_bik,
            "currency": _first_str(acc, "ВалютаДенежныхСредств_Key") or "KZT",
        }

    def _load_organization_details(self, org_key: str) -> dict:
        if not org_key or org_key == "00000000-0000-0000-0000-000000000000":
            return {}
        org = self._get_json(
            f"Catalog_Организации(guid'{org_key}')",
            {"$format": "json"},
        )
        if not org:
            return {}
        acc_key = _first_str(org, "ОсновнойБанковскийСчет_Key")
        bank = self._load_bank_account_details(acc_key) if acc_key else {}
        name = _first_str(org, "НаименованиеПолное", "Description", "Наименование")
        bin_val = _first_str(
            org,
            "БИН",
            "ИНН",
            "ИдентификационныйКодЛичности",
        )
        ci = self._load_contact_info_index().get(_extract_guid_key(org_key), {})
        ip_key = _first_str(org, "ИндивидуальныйПредприниматель_Key")
        ci_ip = (
            self._load_contact_info_index().get(_extract_guid_key(ip_key), {})
            if ip_key
            else {}
        )
        address = _first_str(
            org,
            "ЮридическийАдрес",
            "Адрес",
            "Address",
            "ФактическийАдрес",
        ) or ci.get("address", "") or ci_ip.get("address", "")
        phones = list(ci.get("phones") or ci_ip.get("phones") or [])
        direct = _first_str(org, "Телефон", "Phone", "НомерТелефона")
        if direct:
            display = _contact_phone_display(direct)
            if display:
                seen = {_phone_dedup_key(p) for p in phones}
                key = _phone_dedup_key(direct)
                if not key or key not in seen:
                    phones.insert(0, display)
        return {
            "name": name,
            "bin": bin_val,
            "kbe": _first_str(org, "КБЕ", "kbe"),
            "address": address,
            "phones": phones,
            **bank,
        }

    def _load_counterparty_details(self, cp_key: str) -> dict:
        if not cp_key or cp_key == "00000000-0000-0000-0000-000000000000":
            return {}
        payload = self._get_json(
            f"Catalog_Контрагенты(guid'{cp_key}')",
            {"$format": "json"},
        )
        if not payload:
            return {}
        bin_val = _first_str(
            payload,
            "ИдентификационныйКодЛичности",
            "ИНН",
            "BIN",
            "IdentificationNumber",
        )
        name = _first_str(
            payload,
            "НаименованиеПолное",
            "Description",
            "Наименование",
        )
        kbe = _first_str(payload, "КБЕ", "kbe")
        ci = self._load_contact_info_index().get(_extract_guid_key(cp_key), {})
        address = _first_str(payload, "ЮридическийАдрес", "Адрес", "Address") or ci.get(
            "address", ""
        )
        phones = list(ci.get("phones") or [])
        phone = phones[0] if phones else ci.get("phone", "")
        return {
            "id": cp_key,
            "name": name,
            "bin": bin_val,
            "kbe": kbe,
            "address": address,
            "phone": phone,
            "phones": phones,
        }

    def _load_contract_text(self, contract_key: str) -> str:
        if not contract_key or contract_key == "00000000-0000-0000-0000-000000000000":
            return "Без договора"
        contract = self._get_json(
            f"Catalog_ДоговорыКонтрагентов(guid'{contract_key}')",
            {"$format": "json"},
        )
        if not contract:
            return "Без договора"
        desc = _first_str(contract, "Description", "Наименование").strip()
        if not desc or "без договора" in desc.lower():
            return "Без договора"
        number = (_first_str(contract, "НомерДоговора") or "").strip()
        date_raw = _first_str(contract, "ДатаДоговора")
        if number and date_raw and not date_raw.startswith("0001"):
            date_part = date_raw.split("T")[0]
            try:
                date_part = datetime.strptime(date_part, "%Y-%m-%d").strftime("%d.%m.%Y")
            except ValueError:
                pass
            if date_part not in desc:
                return f"Договор №{number} от {date_part}"
        return desc

    def get_invoice_counterparty_id(self, invoice_id: str) -> Optional[str]:
        # invoice_id here can be a raw path param from GET /api/1c/invoices/{id}/download
        # (via assert_invoice_belongs_to_counterparty) — treat a non-GUID value as
        # "not found" rather than interpolating it into the OData request (see
        # _guid_literal docstring; audit from 2026-08-25).
        try:
            invoice_id = _guid_literal(invoice_id, "invoice_id")
        except ValidationError:
            return None
        header = self._get_json(
            f"{self.INVOICE_DOCUMENT_ENTITY}(guid'{invoice_id}')",
            {"$format": "json"},
        )
        if not header:
            for entity in self.PREFERRED_INVOICE_ENTITIES:
                if entity == self.INVOICE_DOCUMENT_ENTITY:
                    continue
                header = self._get_json(f"{entity}(guid'{invoice_id}')", {"$format": "json"})
                if header:
                    break
        if not header:
            return None
        return _first_str(header, "Контрагент_Key", "Counterparty_Key") or None

    def fetch_invoice_payment_status(
        self,
        invoice_id: str,
        *,
        due_day: int = 5,
        payment_since: Optional[str] = None,
        payment_until: Optional[str] = None,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
        period: Optional[str] = None,
    ) -> Optional[Invoice]:
        """Live-проверка одного счёта из 1С по GUID, без полного списка."""
        try:
            key = _guid_literal(invoice_id, "invoice_id")
        except ValidationError:
            return None
        header = self._get_json(
            f"{self.INVOICE_DOCUMENT_ENTITY}(guid'{key}')",
            {"$format": "json"},
        )
        if not header:
            for entity in self.PREFERRED_INVOICE_ENTITIES:
                if entity == self.INVOICE_DOCUMENT_ENTITY:
                    continue
                header = self._get_json(f"{entity}(guid'{key}')", {"$format": "json"})
                if header:
                    break
        if not header:
            return None
        if not _first_str(header, "Ref_Key", "Ref", "Key", "id"):
            header = dict(header)
            header["Ref_Key"] = key
        inv = self._row_to_invoice(header)
        try:
            inv.items = self.fetch_invoice_line_items(key)
        except Exception:
            pass
        enriched = self._enrich_invoices_payment_status(
            [inv],
            due_day=due_day,
            payment_since=payment_since,
            payment_until=payment_until,
            utilities_due_day=utilities_due_day,
            operations_due_day=operations_due_day,
            period=period,
        )
        return enriched[0] if enriched else inv

    def _build_invoice_pdf_payload(self, invoice_id: str) -> Optional[dict]:
        invoice_id = _guid_literal(invoice_id, "invoice_id")
        header = self._get_json(
            f"{self.INVOICE_DOCUMENT_ENTITY}(guid'{invoice_id}')",
            {"$format": "json"},
        )
        if not header:
            for entity in self.PREFERRED_INVOICE_ENTITIES:
                if entity == self.INVOICE_DOCUMENT_ENTITY:
                    continue
                header = self._get_json(f"{entity}(guid'{invoice_id}')", {"$format": "json"})
                if header:
                    break
        if not header:
            logger.debug(f" OData: invoice {invoice_id} not found for PDF")
            return None

        cp_key = _first_str(header, "Контрагент_Key", "Counterparty_Key")
        buyer = self._load_counterparty_details(cp_key)
        cp_name = buyer.get("name") or self._fetch_counterparty_name(cp_key)
        org_key = _first_str(header, "Организация_Key")
        supplier = self._load_organization_details(org_key)
        contract_key = _first_str(header, "ДоговорКонтрагента_Key")
        contract_text = self._load_contract_text(contract_key)
        payment_knp = _first_str(header, "КодНазначенияПлатежа", "КНП", "KNP")
        date_val = _first_str(header, "Date", "Дата")
        if "T" in date_val:
            date_val = date_val.split("T")[0]

        items = []
        vat_from_lines = 0.0
        for part, name_keys in (
            ("Услуги", ("Содержание", "Номенклатура_Description", "Description")),
            ("Товары", ("Номенклатура_Description", "Содержание", "Description")),
        ):
            for row in self._fetch_invoice_tabular_lines(invoice_id, part):
                row_vat = _extract_vat_from_row(row)
                if row_vat:
                    vat_from_lines += float(row_vat)
                items.append(
                    {
                        "name": _first_str(row, *name_keys),
                        "code": _first_str(row, "Номенклатура_Code", "Код", "Code"),
                        "quantity": _first_float(row, "Количество", "Quantity") or 1,
                        "price": _first_float(row, "Цена", "Price"),
                        "amount": _first_float(row, "Сумма", "Amount"),
                        "unit": _first_str(row, "ЕдиницаИзмерения", "Единица") or "услуга",
                    }
                )

        vat = _first_float(
            header,
            "СуммаНДС",
            "НДС",
            "СуммаНДСДокумента",
            "VAT",
            "СуммаНалога",
            "СуммаНалогов",
            "TaxAmount",
        )
        if not vat and vat_from_lines:
            vat = float(vat_from_lines)

        return {
            "id": invoice_id,
            "number": _first_str(header, "Number", "Номер"),
            "date": date_val,
            "counterparty_id": cp_key,
            "counterparty_name": cp_name,
            "counterparty_bin": buyer.get("bin", ""),
            "counterparty_kbe": buyer.get("kbe", ""),
            "counterparty_address": buyer.get("address", ""),
            "counterparty_phone": buyer.get("phone", ""),
            "supplier_phones": supplier.get("phones", []),
            "contract_text": contract_text,
            "payment_knp": payment_knp,
            "amount": _first_float(header, "СуммаДокумента", "Amount", "Сумма"),
            "vat": vat,
            "currency": "KZT",
            "items": items,
            "supplier": supplier,
            "supplier_name": supplier.get("name", ""),
            "supplier_bin": supplier.get("bin", ""),
            "supplier_kbe": supplier.get("kbe", ""),
            "supplier_iik": supplier.get("iik", ""),
            "supplier_bank_name": supplier.get("bank_name", ""),
            "supplier_bik": supplier.get("bank_bik", ""),
            "supplier_address": supplier.get("address", ""),
        }

    def download_invoice_file(
        self,
        invoice_id: str,
        pdf_path: Optional[str] = None,
        save_path: Optional[str] = None,
        tenant=None,
        force: bool = False,
    ) -> Optional[str]:
        # invoice_id may be a raw path param from a public download endpoint (see
        # payments.py:download_1c_invoice / admin.py:refresh_invoice_pdf) —
        # validate before it's used both as an OData guid-literal below and as a
        # filename component in _resolve_downloads_path (an un-validated value
        # there would also be a path-traversal risk via "../"). See audit from
        # 2026-08-25.
        invoice_id = _guid_literal(invoice_id, "invoice_id")
        if save_path is None:
            save_path = str(self._resolve_downloads_path(invoice_id))
        else:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        out = Path(save_path)
        if out.suffix.lower() != ".pdf":
            out = out.with_suffix(".pdf")
            save_path = str(out)

        # Кэш структурированных данных счёта — раньше этот путь ВСЕГДА
        # перегенерировал файл, своего кэша не было вообще (в отличие от
        # Nova-клиента с файловым PDF-кэшем) — каждый показ каждого счёта
        # безусловно бил в живую OData. См. app/services/invoice_pdf_cache.py.
        # get_cached_payload сама подмешивает реквизиты поставщика из ТЕКУЩЕЙ
        # записи tenant — раньше этот метод _merge_supplier_requisites вообще
        # не вызывал (только Nova-путь), так что арендаторы на OData
        # дополнительно ПОЛУЧАЮТ этот фоллбэк — намеренное расширение, не
        # баг (см. invoice_pdf_cache.py докстринг).
        if not force and tenant is not None:
            from app.db.database import SessionLocal
            from app.services.invoice_pdf_cache import get_cached_payload

            cache_db = SessionLocal()
            try:
                cached_payload = get_cached_payload(cache_db, tenant, invoice_id)
            finally:
                cache_db.close()
            if cached_payload:
                from app.services.invoice_report import generate_formal_invoice_document

                generated = generate_formal_invoice_document(cached_payload, save_path, tenant)
                if generated and Path(generated).is_file():
                    logger.info("OData: PDF счёта %s из кэша структурированных данных", invoice_id)
                    return generated
                logger.warning(
                    "OData: рендер из кэша payload'а не удался для %s — живой путь", invoice_id
                )

        if out.exists():
            out.unlink()

        payload = self._build_invoice_pdf_payload(invoice_id)
        if not payload:
            return None

        if tenant is not None:
            from app.db.database import SessionLocal
            from app.services.invoice_pdf_cache import store_payload_if_valid

            cache_db = SessionLocal()
            try:
                store_payload_if_valid(
                    cache_db, tenant.id, invoice_id, dict(payload), source="odata", tenant=tenant
                )
            except Exception:
                logger.debug("OData: invoice_pdf_cache store failed for %s", invoice_id, exc_info=True)
            finally:
                cache_db.close()

        try:
            from app.services.invoice_report import generate_formal_invoice_document

            formal = generate_formal_invoice_document(payload, save_path, tenant)
            if formal:
                logger.info("OData: formal invoice PDF: %s", formal)
                return formal
            logger.warning(
                "OData: formal invoice unavailable for %s, using simple PDF fallback",
                invoice_id,
            )
        except Exception as e:
            logger.warning("OData: formal invoice failed for %s, fallback: %s", invoice_id, e)

        try:
            result = generate_invoice_pdf(payload, save_path)
            logger.warning("OData: simple PDF fallback generated: %s", result)
            return result
        except Exception as e:
            logger.debug(f" OData: failed to generate PDF: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _contact_info_available(self) -> bool:
        discovered = self._discover_entity_sets()
        return self.CONTACT_INFO_ENTITY in discovered

    def _invalidate_contact_info_cache(self) -> None:
        self._contact_info_index = None

    def _contact_record_path(
        self,
        counterparty_id: str,
        kind_vid: str,
        *,
        contact_type: str = "Телефон",
    ) -> str:
        cp_id = _extract_guid_key(counterparty_id)
        return (
            f"{quote(self.CONTACT_INFO_ENTITY, safe='')}"
            f"(Объект=guid'{cp_id}',Тип='{contact_type}',Вид=guid'{kind_vid}',"
            f"Объект_Type='{self.COUNTERPARTY_OBJECT_TYPE}',"
            f"Вид_Type='{self.CONTACT_KIND_OBJECT_TYPE}')"
        )

    def _request_odata(
        self,
        method: str,
        entity_path: str,
        *,
        body: Optional[dict] = None,
    ) -> tuple[int, str]:
        self._ensure_connected()
        url = f"{self._base_url}/{entity_path}"
        response = self._session.request(
            method,
            url,
            json=body,
            params={"$format": "json"},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=self._timeout,
        )
        return response.status_code, (response.text or "")[:500]

    def _counterparty_phone_contact_rows(self, counterparty_id: str) -> List[dict]:
        if not self._contact_info_available():
            return []
        cp_key = _extract_guid_key(counterparty_id)
        rows = self._fetch_entity_rows(
            self.CONTACT_INFO_ENTITY,
            {"$format": "json"},
            max_rows=self.DEFAULT_FETCH_LIMIT,
        )
        result: List[dict] = []
        for row in rows:
            if _contact_owner_key(row) != cp_key:
                continue
            if (row.get("Тип") or "").strip().lower() != "телефон":
                continue
            result.append(row)
        return result

    def _phone_display_for_1c(self, phone: str) -> str:
        display = _contact_phone_display(phone) or _normalize_phone(phone) or phone.strip()
        return display

    def _pick_phone_contact_kind(
        self,
        existing_rows: List[dict],
        *,
        preferred_kind: Optional[str] = None,
    ) -> str:
        if preferred_kind:
            return preferred_kind
        if existing_rows:
            for kind in self.PHONE_CONTACT_KINDS:
                if any(_contact_kind_key(row) == kind for row in existing_rows):
                    return kind
            kind = _contact_kind_key(existing_rows[0])
            if kind:
                return kind
        for kind in self.PHONE_CONTACT_KINDS:
            if not any(_contact_kind_key(row) == kind for row in existing_rows):
                return kind
        return self.PHONE_CONTACT_KINDS[0]

    def upsert_counterparty_phone(
        self,
        counterparty_id: str,
        phone: str,
        *,
        kind_vid: Optional[str] = None,
    ) -> dict:
        """
        Создать или обновить телефон контрагента в регистре контактной информации 1С.
        """
        cp_id = _extract_guid_key(counterparty_id)
        display = self._phone_display_for_1c(phone)
        if not cp_id or not display:
            return {"ok": False, "action": "error", "message": "Некорректный контрагент или телефон"}
        if not self._contact_info_available():
            return {
                "ok": False,
                "action": "skip",
                "message": "В OData не опубликован регистр контактной информации",
            }

        target_key = _phone_dedup_key(display)
        existing = self._counterparty_phone_contact_rows(cp_id)
        for row in existing:
            current = self._phone_display_for_1c(row.get("Представление") or "")
            if _phone_dedup_key(current) == target_key:
                return {"ok": True, "action": "skip", "message": "Телефон уже есть в 1С"}

        kind = self._pick_phone_contact_kind(existing, preferred_kind=kind_vid)
        body = {
            "Объект": cp_id,
            "Объект_Type": self.COUNTERPARTY_OBJECT_TYPE,
            "Тип": "Телефон",
            "Вид": kind,
            "Вид_Type": self.CONTACT_KIND_OBJECT_TYPE,
            "Представление": display,
            "ЗначениеПоУмолчанию": True,
        }
        same_kind = next(
            (row for row in existing if _contact_kind_key(row) == kind),
            None,
        )
        if same_kind:
            status, detail = self._request_odata(
                "PATCH",
                self._contact_record_path(cp_id, kind),
                body={"Представление": display, "ЗначениеПоУмолчанию": True},
            )
            action = "update"
        else:
            status, detail = self._request_odata(
                "POST",
                quote(self.CONTACT_INFO_ENTITY, safe=""),
                body=body,
            )
            action = "create"

        if status in (200, 201, 204):
            self._invalidate_contact_info_cache()
            return {"ok": True, "action": action, "message": ""}

        logger.warning(
            "OData phone %s failed for cp=%s kind=%s: HTTP %s %s",
            action,
            cp_id,
            kind,
            status,
            detail,
        )
        return {
            "ok": False,
            "action": action,
            "message": f"1С отклонила сохранение телефона (HTTP {status})",
        }

    def get_swagger(self) -> dict:
        return {"type": "odata", "base_url": self._base_url}
