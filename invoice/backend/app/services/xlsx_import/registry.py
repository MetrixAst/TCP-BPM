"""Какой парсер понимает файлы какого арендатора — по Tenant.xlsx_parser_key
(строка, а не org_id/trc_id: формат файла — свойство того, кто и как его
составляет у ТЦ, см. app/models/catalog.py). Новый ТЦ на xlsx = новый модуль
в parsers/ + одна строка здесь, ядро (normalize/upsert) не трогается."""
from __future__ import annotations

from typing import Callable

from app.services.xlsx_import.parsers import avantage, maxi_mall
from app.services.xlsx_import.types import ParseResult

PARSERS: dict[str, Callable[[bytes], ParseResult]] = {
    maxi_mall.PARSER_KEY: maxi_mall.parse,
    avantage.PARSER_KEY: avantage.parse,
}


def get_parser(parser_key: str) -> Callable[[bytes], ParseResult]:
    parser = PARSERS.get(parser_key)
    if parser is None:
        raise ValueError(
            f'Неизвестный xlsx_parser_key "{parser_key}" — доступны: {", ".join(PARSERS) or "(нет)"}'
        )
    return parser
