import json
from functools import lru_cache
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent / 'locale'
SUPPORTED_LANGS = ('ru', 'kk', 'en')
DEFAULT_LANG = 'ru'


@lru_cache(maxsize=8)
def _load_locale(lang: str) -> dict:
    path = LOCALE_DIR / f'{lang}.json'
    if not path.exists():
        path = LOCALE_DIR / f'{DEFAULT_LANG}.json'
    with path.open(encoding='utf-8') as fh:
        return json.load(fh)


def _lookup(messages: dict, key: str):
    node = messages
    for part in key.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def translate(lang: str, key: str, default=None, **kwargs) -> str:
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    value = _lookup(_load_locale(lang), key)
    if value is None and lang != DEFAULT_LANG:
        value = _lookup(_load_locale(DEFAULT_LANG), key)
    if value is None:
        value = default if default is not None else key
    if not isinstance(value, str):
        return str(value)
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, ValueError):
            return value
    return value


def build_lang_url(request, lang: str) -> str:
    params = request.GET.copy()
    params['lang'] = lang
    query = params.urlencode()
    return request.path + (f'?{query}' if query else '')
