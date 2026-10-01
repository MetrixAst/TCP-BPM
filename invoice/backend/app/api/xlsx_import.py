"""Self-serve загрузка .xlsx как альтернативного источника данных — см.
app/services/xlsx_import/. ТЦ грузит файл через invoice-client, дальше
parse -> normalize -> upsert синхронно в запросе (тот же файл — доли
секунды на реальных объёмах Maxi Mall, отдельная очередь не нужна, см.
app/services/xlsx_import/__init__.py)."""
from __future__ import annotations

import logging
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session

from app.api.deps import security_scheme
from app.api.tenant_scope import get_portal_tenant_ids, scoped_tenant_id
from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.catalog import Tenant
from app.schemas.xlsx_import import XlsxImportSummaryResponse
from app.services.xlsx_import import import_tenant_file
from app.services.xlsx_import.storage import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    save_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _describe_uploader(
    db: Session,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    portal = get_portal_tenant_ids(credentials)
    if portal:
        if portal.get("role") == "trc":
            return f'trc:{portal["trc_id"]}'
        return f'tenant:{portal.get("tenant_id")}'
    token = credentials.credentials if credentials else None
    username = decode_access_token(token) if token else None
    return f"admin:{username}" if username else "unknown"


@router.post("/upload", response_model=XlsxImportSummaryResponse)
async def upload_xlsx(
    file: UploadFile = File(...),
    tenant_id: Optional[int] = Depends(scoped_tenant_id),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
):
    # scoped_tenant_id уже закрывает межарендаторскую утечку (см. фикс
    # resolve_tenant_id от 2026-08-26) — но "без ограничения" (админский JWT
    # без ?tenant_id) для ЭТОГО эндпоинта не имеет смысла: загрузка всегда
    # про конкретного арендатора, "загрузить непонятно кому" — не операция.
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Не указан tenant_id")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active.is_(True)).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Арендатор не найден")
    if not tenant.xlsx_parser_key:
        raise HTTPException(
            status_code=400,
            detail="Загрузка xlsx для этого арендатора не настроена — обратитесь в поддержку Metrix",
        )

    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Ожидается файл .xlsx")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой (максимум {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ)",
        )

    data_file = save_upload(
        db,
        tenant_id=tenant_id,
        original_filename=filename,
        file_bytes=file_bytes,
        uploaded_by=_describe_uploader(db, credentials),
    )

    try:
        summary = import_tenant_file(db, tenant, file_bytes)
    except (ValueError, zipfile.BadZipFile, InvalidFileException, KeyError) as exc:
        # Всё, что говорит "это не тот файл/не тот формат" — клиентская
        # ошибка (422), а не наш баг: не .xlsx вовсе (BadZipFile — xlsx это
        # zip-контейнер), xlsx, но без нужных листов/колонок (ValueError из
        # парсера/registry), либо неожиданная структура листа (KeyError).
        data_file.status = "failed"
        data_file.error = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Не удалось разобрать файл: {exc}") from exc
    except Exception:
        data_file.status = "failed"
        data_file.error = "Внутренняя ошибка при обработке файла"
        db.commit()
        logger.exception("xlsx import failed tenant_id=%s file_id=%s", tenant_id, data_file.id)
        raise HTTPException(status_code=500, detail="Не удалось обработать файл") from None

    data_file.status = "parsed_with_errors" if (summary.warnings or summary.rows_unmatched) else "parsed_ok"
    import json

    data_file.parse_summary = json.dumps(
        {
            "periods": summary.periods,
            "rows_total": summary.rows_total,
            "rows_matched": summary.rows_matched,
            "rows_unmatched": summary.rows_unmatched,
            "rows_deleted": summary.rows_deleted,
        },
        ensure_ascii=False,
    )
    db.commit()

    return XlsxImportSummaryResponse(
        file_id=data_file.id,
        tenant_id=tenant_id,
        periods=summary.periods,
        rows_total=summary.rows_total,
        rows_created=summary.rows_created,
        rows_updated=summary.rows_updated,
        rows_deleted=summary.rows_deleted,
        rows_matched=summary.rows_matched,
        rows_unmatched=summary.rows_unmatched,
        unmatched_names=summary.unmatched_names,
        totals_check=summary.totals_check,
        warnings=summary.warnings,
    )
