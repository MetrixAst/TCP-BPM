"""Интеграция с ONLYOFFICE Document Server.

Серверное редактирование документов: файл хранится на нашем сервере, открывается
и сохраняется через Document Server (Docker), наружу (Google Viewer и т.п.) не уходит.

Поток данных:
  * Браузер  -> Document Server (api.js, iframe редактора)  — `DS_PUBLIC_URL`
  * Document Server -> Django (скачать файл, callback на сохранение) — `BACKEND_INTERNAL_URL`

Конфиг редактора подписывается JWT (общий секрет с Document Server), если включён.
"""

import hashlib
import os

from django.conf import settings

try:
    import jwt
except ImportError:  # pragma: no cover - PyJWT присутствует в requirements
    jwt = None


# Сопоставление расширения -> тип документа редактора ONLYOFFICE.
_WORD = {
    'doc', 'docm', 'docx', 'docxf', 'dot', 'dotm', 'dotx', 'epub', 'fodt',
    'htm', 'html', 'mht', 'mhtml', 'odt', 'ott', 'rtf', 'txt', 'fb2', 'xml',
}
_CELL = {
    'csv', 'fods', 'ods', 'ots', 'xls', 'xlsb', 'xlsm', 'xlsx', 'xlt',
    'xltm', 'xltx',
}
_SLIDE = {
    'fodp', 'odp', 'otp', 'pot', 'potm', 'potx', 'pps', 'ppsm', 'ppsx',
    'ppt', 'pptm', 'pptx',
}
_PDF = {'pdf', 'djvu', 'oxps', 'xps'}

# Что можно открывать на редактирование (а не только просмотр).
_EDITABLE = {
    'docx', 'docm', 'dotx', 'odt', 'ott', 'rtf', 'txt', 'fodt',
    'xlsx', 'xlsm', 'xltx', 'ods', 'ots', 'csv', 'fods',
    'pptx', 'ppsx', 'potx', 'odp', 'otp', 'fodp',
}


def is_enabled():
    """ONLYOFFICE подключён, если задан публичный URL Document Server."""
    return bool(getattr(settings, 'ONLYOFFICE_DS_PUBLIC_URL', ''))


def jwt_enabled():
    return bool(getattr(settings, 'ONLYOFFICE_JWT_ENABLED', False)) and bool(
        getattr(settings, 'ONLYOFFICE_JWT_SECRET', '')
    ) and jwt is not None


def get_extension(filename):
    if not filename:
        return ''
    return os.path.splitext(filename)[1].lstrip('.').lower()


def get_document_type(ext):
    """Тип документа для редактора: word / cell / slide / pdf."""
    ext = (ext or '').lower()
    if ext in _CELL:
        return 'cell'
    if ext in _SLIDE:
        return 'slide'
    if ext in _PDF:
        return 'pdf'
    if ext in _WORD:
        return 'word'
    return ''


def is_supported(filename):
    return get_document_type(get_extension(filename)) != ''


def is_editable(filename):
    return get_extension(filename) in _EDITABLE


def public_api_url():
    """URL скрипта api.js Document Server для браузера."""
    base = getattr(settings, 'ONLYOFFICE_DS_PUBLIC_URL', '').rstrip('/')
    return f'{base}/web-apps/apps/api/documents/api.js'


def _backend_url(request, relative_url):
    """Абсолютный URL, доступный Document Server'у (а не только браузеру)."""
    internal = getattr(settings, 'ONLYOFFICE_BACKEND_INTERNAL_URL', '').rstrip('/')
    if internal:
        return f'{internal}{relative_url}'
    return request.build_absolute_uri(relative_url)


def build_key(document):
    """Уникальный ключ версии документа.

    Меняется при изменении файла, чтобы Document Server перечитал содержимое.
    """
    parts = [str(document.pk), document.document.name or '']
    try:
        storage = document.document.storage
        name = document.document.name
        parts.append(str(storage.size(name)))
        try:
            parts.append(storage.get_modified_time(name).isoformat())
        except Exception:
            pass
    except Exception:
        pass
    digest = hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()
    return f'{document.pk}-{digest}'[:128]


def sign(payload):
    """Подпись JWT для тела/конфига (HS256)."""
    if not jwt_enabled():
        return None
    return jwt.encode(payload, settings.ONLYOFFICE_JWT_SECRET, algorithm='HS256')


def decode(token):
    """Проверка и декодирование JWT из callback. Бросает исключение при ошибке."""
    return jwt.decode(token, settings.ONLYOFFICE_JWT_SECRET, algorithms=['HS256'])


def _user_image(request, user):
    """Публичный URL аватара для отображения в редакторе (грузится браузером)."""
    try:
        avatar = user.get_avatar_url or ''
    except Exception:
        avatar = ''
    if avatar:
        return request.build_absolute_uri(avatar)
    return '/img/avatar.svg'


def build_config(request, document, can_edit, callback_relative_url):
    """Сборка конфигурации редактора ONLYOFFICE.

    Структура повторяет рабочий конфиг проекта (см. backend/ONLYOFFICE.html и
    generateTokenJWT.txt): events / document / documentType / editorConfig,
    весь объект подписывается JWT (HS256).
    """
    filename = os.path.basename(document.document.name)
    ext = get_extension(filename)
    editable = can_edit and is_editable(filename)

    user = request.user
    config = {
        'events': {},
        'document': {
            'fileType': ext,
            'key': build_key(document),
            'title': document.title or filename,
            'url': _backend_url(request, document.document.url),
            'permissions': {
                'edit': editable,
                'download': True,
                'print': True,
                'comment': editable,
                'chat': False,
            },
        },
        'documentType': get_document_type(ext),
        'editorConfig': {
            'lang': getattr(request, 'current_lang', None) or 'ru',
            'mode': 'edit' if editable else 'view',
            'callbackUrl': _backend_url(request, callback_relative_url),
            'autosave': editable,
            'autosaveInterval': 240,
            'user': {
                'id': str(getattr(user, 'id', '') or 'anon'),
                'name': (getattr(user, 'get_name', None) and user.get_name)
                or getattr(user, 'username', '') or 'Пользователь',
                'image': _user_image(request, user),
            },
            'customization': {
                'anonymousEditing': False,
                'integrationMode': 'embed',
                'uiTheme': {'theme': 'theme-light', 'mode': 'light'},
                'close': {'visible': True, 'text': 'Закрыть'},
                'forcesave': True,
            },
        },
    }

    token = sign(config)
    if token:
        config['token'] = token
    return config
