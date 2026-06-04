"""
Генерация PDF для выставленных счетов (preview и скачивание).
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.template.loader import render_to_string
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

ISSUER_NAME = getattr(settings, 'INVOICE_ISSUER_NAME', 'ТОО «ТРЦ Метрикс»')
ISSUER_BIN = getattr(settings, 'INVOICE_ISSUER_BIN', '')
ISSUER_ADDRESS = getattr(settings, 'INVOICE_ISSUER_ADDRESS', 'г. Алматы, Республика Казахстан')

PDF_FONT_FAMILY = 'InvoiceFont'


def _resolve_pdf_font_path() -> Path | None:
    """TTF с поддержкой кириллицы (встраивается в PDF через xhtml2pdf)."""
    base = Path(settings.BASE_DIR)
    candidates = [
        base / 'static' / 'site' / 'fonts' / 'NotoSans-Regular.ttf',
        base / 'static' / 'site' / 'fonts' / 'DejaVuSans.ttf',
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        Path('/usr/share/fonts/TTF/DejaVuSans.ttf'),
        Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
        Path('/Library/Fonts/Arial.ttf'),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _pdf_link_callback(uri: str, rel: str, font_path: Path) -> str | None:
    """
    xhtml2pdf не подхватывает кириллицу через file:// в @font-face.
    Возвращаем локальный путь к TTF, чтобы шрифт встроился в PDF.
    """
    if uri.startswith('file://'):
        local = unquote(urlparse(uri).path)
        if Path(local).is_file():
            return local

    name = Path(uri).name
    if name == font_path.name:
        return str(font_path)

    sibling = font_path.parent / name
    if sibling.is_file():
        return str(sibling)

    return None


def build_invoice_pdf(invoice) -> bytes:
    """
    Собирает PDF из HTML-шаблона. Возвращает байты PDF.
    """
    font_path = _resolve_pdf_font_path()
    if not font_path:
        logger.error('invoice_pdf_no_font: no TTF with Cyrillic support found')
        raise ValueError(
            'Не найден шрифт для PDF. Добавьте NotoSans-Regular.ttf в static/site/fonts/.'
        )

    font_filename = font_path.name
    font_dir = str(font_path.parent)

    html = render_to_string(
        'finances/pdf/invoice.html',
        {
            'invoice': invoice,
            'items': invoice.items.all(),
            'issuer_name': ISSUER_NAME,
            'issuer_bin': ISSUER_BIN,
            'issuer_address': ISSUER_ADDRESS,
            'pdf_font_family': PDF_FONT_FAMILY,
            'pdf_font_file': font_filename,
            'lang': lang,
        },
    )

    link_callback = lambda uri, rel: _pdf_link_callback(uri, rel, font_path)

    result = BytesIO()
    pdf_status = pisa.CreatePDF(
        html,
        dest=result,
        encoding='utf-8',
        link_callback=link_callback,
        path=font_dir,
    )
    if pdf_status.err:
        logger.error('invoice_pdf_error: invoice_id=%s err=%s', invoice.pk, pdf_status.err)
        raise ValueError('Не удалось сформировать PDF')

    pdf_bytes = result.getvalue()
    if b'WinAnsiEncoding' in pdf_bytes and b'TrueType' not in pdf_bytes and b'Type0' not in pdf_bytes:
        logger.warning(
            'invoice_pdf_font_fallback: invoice_id=%s font=%s',
            invoice.pk,
            font_path,
        )

    return pdf_bytes
