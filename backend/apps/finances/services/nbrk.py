import logging
import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

NBRK_URL = "https://nationalbank.kz/rss/get_rates.cfm"


class NBRKServiceError(Exception):
    pass


def fetch_nbrk_rates(
    date: datetime.date | None = None,
    currencies: list[str] | None = None,
) -> list[dict]:
    target_date = date or datetime.date.today()
    params = {
        "ftype": "0",
        "showdate": target_date.strftime("%d.%m.%Y"),
    }

    logger.info("Запрос к НБ РК за %s", params["showdate"])

    try:
        response = requests.get(NBRK_URL, params=params, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NBRKServiceError(f"Ошибка запроса к НБ РК: {exc}") from exc

    raw = response.content.lstrip()
    if raw.startswith(b"{"):
        raise NBRKServiceError(
            f"НБ РК вернул ошибку вместо XML: {response.text[:300]}"
        )

    return _parse_xml(response.content, currencies=currencies)


def _parse_xml(
    content: bytes,
    currencies: list[str] | None = None,
) -> list[dict]:
    filter_set = {c.upper() for c in currencies} if currencies else set()

    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise NBRKServiceError(f"Не удалось разобрать XML от НБ РК: {exc}") from exc

    # Дата из заголовка XML
    header_date: datetime.date | None = None
    date_el = root.find("date")
    if date_el is not None and date_el.text:
        try:
            header_date = datetime.datetime.strptime(date_el.text.strip(), "%d.%m.%Y").date()
        except ValueError:
            logger.warning("Не удалось распарсить дату из XML: %s", date_el.text)

    results = []

    for item in root.findall("item"):
        title_el = item.find("title")
        units_el = item.find("units")
        quant_el = item.find("quant")

        if title_el is None or units_el is None:
            continue

        currency_code = (title_el.text or "").strip().upper()
        if not currency_code:
            continue

        if filter_set and currency_code not in filter_set:
            continue

        try:
            units = Decimal(str(units_el.text).strip().replace(",", "."))
        except (InvalidOperation, AttributeError):
            logger.warning("Некорректный курс для %s: %s", currency_code, units_el.text)
            continue

        quant = 1
        if quant_el is not None and quant_el.text:
            try:
                quant = int(quant_el.text.strip())
            except ValueError:
                pass

        rate = (units / Decimal(quant)).quantize(Decimal("0.0001"))

        results.append({
            "currency": currency_code,
            "date": header_date,
            "rate": rate,
        })

    logger.info("НБ РК: получено %d курсов за %s", len(results), header_date)
    return results


def save_rates(rates: list[dict]) -> tuple[int, int]:
    from finances.models import ExchangeRate

    created = updated = 0

    for item in rates:
        if not item.get("date") or not item.get("currency") or item.get("rate") is None:
            logger.warning("Пропускаем некорректную запись: %s", item)
            continue

        _, was_created = ExchangeRate.objects.update_or_create(
            currency=item["currency"],
            date=item["date"],
            defaults={"rate": item["rate"]},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("Курсы сохранены: создано=%d, обновлено=%d", created, updated)
    return created, updated


def fetch_and_save_rates(
    date: datetime.date | None = None,
    currencies: list[str] | None = None,
) -> tuple[int, int]:
    rates = fetch_nbrk_rates(date=date, currencies=currencies)
    return save_rates(rates)