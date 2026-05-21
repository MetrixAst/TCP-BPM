"""
Сервис получения курсов валют Национального банка Республики Казахстан.

XML-endpoint: https://nationalbank.kz/rss/get_rates.cfm?fdate=DD.MM.YYYY
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation

import requests

logger = logging.getLogger(__name__)

NBRK_URL = "https://nationalbank.kz/rss/get_rates.cfm"

TRACKED_CURRENCIES = {'USD', 'EUR', 'RUB', 'CNY', 'GBP', 'CHF'}


def fetch_nbrk_rates(target_date: date | None = None) -> list[dict]:
    """
    Запрашивает XML с курсами НБ РК за указанную дату (по умолчанию — сегодня).

    Возвращает список словарей вида:
        [{'currency': 'USD', 'date': date(...), 'rate': Decimal('...'), 'source': 'nbrk'}, ...]
    """
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime('%d.%m.%Y')
    url = f"{NBRK_URL}?fdate={date_str}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error(f"nbrk_fetch_error: {exc}")
        raise

    return _parse_nbrk_xml(response.text, target_date)


def _parse_nbrk_xml(xml_text: str, target_date: date) -> list[dict]:
    """Разбирает XML-ответ НБ РК и возвращает записи для отслеживаемых валют."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error(f"nbrk_xml_parse_error: {exc}")
        raise ValueError(f"Не удалось разобрать XML НБ РК: {exc}") from exc

    results = []

    # Структура XML: <rates> <item> <title>USD</title> <description>475.46</description> ...
    for item in root.iter('item'):
        title_el = item.find('title')
        desc_el  = item.find('description')

        if title_el is None or desc_el is None:
            continue

        currency = (title_el.text or '').strip().upper()
        rate_raw = (desc_el.text or '').strip().replace(',', '.')

        if currency not in TRACKED_CURRENCIES:
            continue

        try:
            rate = Decimal(rate_raw)
        except InvalidOperation:
            logger.warning(f"nbrk_bad_rate: currency={currency} raw={rate_raw!r}")
            continue

        results.append({
            'currency': currency,
            'date':     target_date,
            'rate':     rate,
            'source':   'nbrk',
        })

    logger.info(f"nbrk_parsed: date={target_date} currencies={[r['currency'] for r in results]}")
    return results


def save_nbrk_rates(rates: list[dict]) -> dict:
    """
    Сохраняет полученные курсы в БД через update_or_create.

    Возвращает {'created': int, 'updated': int}.
    """
    from finances.models import ExchangeRate

    created = updated = 0
    for entry in rates:
        _, is_new = ExchangeRate.objects.update_or_create(
            currency=entry['currency'],
            date=entry['date'],
            defaults={'rate': entry['rate'], 'source': entry['source']},
        )
        if is_new:
            created += 1
        else:
            updated += 1

    logger.info(f"nbrk_saved: created={created} updated={updated}")
    return {'created': created, 'updated': updated}
