"""Обратное геокодирование координат в адрес (Nominatim / OpenStreetMap)."""
import logging

import requests

logger = logging.getLogger(__name__)

_ADDRESS_CACHE = {}
_NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
_USER_AGENT = 'metriX-BPM/1.0 (HR attendance)'


def reverse_geocode(latitude, longitude, language='ru'):
    """
    Возвращает человекочитаемый адрес по широте/долготе или пустую строку.
    """
    if latitude is None or longitude is None:
        return ''

    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return ''

    cache_key = (round(lat, 6), round(lng, 6))
    if cache_key in _ADDRESS_CACHE:
        return _ADDRESS_CACHE[cache_key]

    try:
        response = requests.get(
            _NOMINATIM_URL,
            params={
                'lat': lat,
                'lon': lng,
                'format': 'json',
                'accept-language': language,
                'zoom': 18,
            },
            headers={'User-Agent': _USER_AGENT},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
        address = (data.get('display_name') or '').strip()
        if not address and isinstance(data.get('address'), dict):
            parts = data['address']
            chunks = [
                parts.get('road') or parts.get('pedestrian') or parts.get('footway'),
                parts.get('house_number'),
                parts.get('suburb') or parts.get('neighbourhood'),
                parts.get('city') or parts.get('town') or parts.get('village'),
            ]
            address = ', '.join(c for c in chunks if c)
    except Exception as exc:
        logger.warning('reverse_geocode failed: %s', exc)
        address = ''

    _ADDRESS_CACHE[cache_key] = address
    return address


def resolve_location_address(record):
    """Адрес из БД или обратное геокодирование с сохранением в запись."""
    if record.location_address:
        return record.location_address

    if not record.latitude or not record.longitude:
        return ''

    address = reverse_geocode(record.latitude, record.longitude)
    if address:
        from .models import AttendanceRecord
        AttendanceRecord.objects.filter(pk=record.pk).update(location_address=address)
    return address
