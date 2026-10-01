"""Хранение загруженных .xlsx — тот же durability-паттерн, что и
tenant_stamp.py: диск (переживает деплой, но не гарантирован на всех подах
без общего volume) + байты в БД (LargeBinary, фолбэк, если диск не общий)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tenant_data_file import TenantDataFile
from app.services.tenant_stamp import _tenant_assets_root

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 МБ — реальный файл Maxi Mall на порядок меньше
ALLOWED_EXTENSIONS = (".xlsx",)


def _data_files_dir(tenant_id: int) -> Path:
    path = _tenant_assets_root() / str(tenant_id) / "data-files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(
    db: Session,
    *,
    tenant_id: int,
    original_filename: str,
    file_bytes: bytes,
    uploaded_by: Optional[str],
) -> TenantDataFile:
    """Новая версия — старые не трём (аудит/откат), деактивируем их
    is_active вместо удаления. Диск может не быть общим на всех подах —
    file_bytes в БД остаётся авторитетным источником для чтения обратно."""
    db.query(TenantDataFile).filter(
        TenantDataFile.tenant_id == tenant_id, TenantDataFile.is_active.is_(True)
    ).update({"is_active": False})

    row = TenantDataFile(
        tenant_id=tenant_id,
        original_filename=original_filename,
        file_bytes=file_bytes,
        uploaded_by=uploaded_by,
        status="pending",
        is_active=True,
    )
    db.add(row)
    db.flush()

    try:
        target_dir = _data_files_dir(tenant_id)
        path = target_dir / f"{row.id}_{original_filename}"
        path.write_bytes(file_bytes)
        row.storage_path = str(path.resolve())
    except OSError as exc:
        logger.warning(
            "xlsx upload saved to DB but disk write failed (tenant_id=%s file_id=%s): %s",
            tenant_id, row.id, exc,
        )

    db.commit()
    db.refresh(row)
    return row
