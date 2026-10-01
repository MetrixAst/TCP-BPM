from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class XlsxImportSummaryResponse(BaseModel):
    file_id: int
    tenant_id: int
    periods: List[str]
    rows_total: int
    rows_created: int
    rows_updated: int
    # Полная замена, не патч — старые xlsx-строки этого арендатора, которых
    # нет в новом файле, удаляются (см. xlsx_import/upsert.py). 0 обычно
    # означает "новый файл содержит всё то же, что и старый" — не "ничего
    # не сделано".
    rows_deleted: int
    rows_matched: int
    rows_unmatched: int
    unmatched_names: List[str]
    # ключ вида "ИЮНЬ:rent" -> {expected, actual, diff (float), ok (bool)} —
    # см. maxi_mall.py. Пусто, если парсер конкретного ТЦ не считает такую
    # самопроверку.
    totals_check: Dict[str, Dict[str, Any]]
    warnings: List[str]


class XlsxDataFileResponse(BaseModel):
    id: int
    original_filename: str
    uploaded_at: str
    status: str
    is_active: bool
    error: Optional[str] = None
