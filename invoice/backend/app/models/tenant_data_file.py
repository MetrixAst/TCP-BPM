"""Загруженные ТЦ .xlsx-файлы — источник данных наравне с 1С (см.
app/services/xlsx_import/). Каждая загрузка — новая строка (версионирование:
старые не трём, нужны для аудита/отката), is_active отмечает, какая версия
сейчас реально используется для конкретного tenant_id.

Файл дублируется на диск (uploads/tenants/{tenant_id}/data-files/, тот же
паттерн, что и app/services/tenant_stamp.py для штампа) и байтами в БД —
LargeBinary как durability-фолбэк на случай нескольких подов без общего
диска (см. tenant_stamp.py:34-38 про этот же компромисс)."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.db.database import Base


class TenantDataFile(Base):
    __tablename__ = "tenant_data_files"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String(512), nullable=False)
    storage_path = Column(String(512), nullable=True)
    file_bytes = Column(LargeBinary, nullable=True)
    # Кто загрузил: "tenant:<id>" / "trc:<id>" (портал) / "admin:<username>".
    uploaded_by = Column(String(128), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # pending -> parsed_ok | parsed_with_errors | failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    # {"periods": ["2026-08", ...], "rows_total": N, "rows_matched": N,
    #  "rows_unmatched": [...], "totals_check": {...}} — см. xlsx_import/normalize.py
    parse_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
