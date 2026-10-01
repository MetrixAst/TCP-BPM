from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

ALLOWED_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".png",
    "image/jpg": ".png",
    "image/svg+xml": ".png",
}


def _tenant_assets_root() -> Path:
    custom = (os.getenv("TENANT_UPLOADS_DIR") or "").strip()
    if custom:
        return Path(custom)
    return BACKEND_ROOT / "uploads" / "tenants"


def _cache_dir(tenant_id: int) -> Path:
    return Path(tempfile.gettempdir()) / "tenant_assets" / str(tenant_id)


def _materialize_png(tenant_id: int, basename: str, data: bytes) -> Path:
    path = _cache_dir(tenant_id) / f"{basename}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.resolve()


def tenant_assets_dir(tenant_id: int) -> Path:
    path = _tenant_assets_root() / str(tenant_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_asset_path(file_path: Optional[str]) -> Optional[Path]:
    if not file_path:
        return None
    raw = Path(file_path)
    candidates: list[Path] = [raw]
    if not raw.is_absolute():
        candidates.append(_tenant_assets_root() / raw)
        candidates.append(BACKEND_ROOT / raw)
        candidates.append(_tenant_assets_root() / raw.name)
        if len(raw.parts) >= 2:
            candidates.append(_tenant_assets_root() / raw.parts[-2] / raw.parts[-1])
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def _canonical_asset_path(tenant_id: int, basename: str) -> Path:
    return tenant_assets_dir(tenant_id) / f"{basename}.png"


def _png_from_tenant(tenant: Any, field: str) -> Optional[bytes]:
    data = getattr(tenant, field, None)
    if data:
        return bytes(data)
    return None


def resolve_stamp_path(
    stamp_file_path: Optional[str],
    tenant_id: Optional[int] = None,
    tenant: Any = None,
) -> Optional[Path]:
    if tenant is not None:
        blob = _png_from_tenant(tenant, "stamp_png")
        if blob and tenant_id is not None:
            return _materialize_png(tenant_id, "stamp", blob)
    if tenant_id is not None:
        canonical = _canonical_asset_path(tenant_id, "stamp")
        if canonical.is_file():
            return canonical.resolve()
    return resolve_asset_path(stamp_file_path)


def resolve_signature_path(
    signature_file_path: Optional[str],
    tenant_id: Optional[int] = None,
    tenant: Any = None,
) -> Optional[Path]:
    if tenant is not None:
        blob = _png_from_tenant(tenant, "signature_png")
        if blob and tenant_id is not None:
            return _materialize_png(tenant_id, "signature", blob)
    if tenant_id is not None:
        canonical = _canonical_asset_path(tenant_id, "signature")
        if canonical.is_file():
            return canonical.resolve()
    return resolve_asset_path(signature_file_path)


def _read_upload(file: UploadFile) -> Tuple[bytes, str]:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Допустимы файлы PNG или SVG",
        )
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл больше 5 МБ")
    return raw, content_type


def _to_png_bytes(raw: bytes, content_type: str) -> bytes:
    if content_type in ("image/png", "image/jpeg", "image/jpg"):
        return raw
    try:
        import cairosvg

        return cairosvg.svg2png(bytestring=raw)
    except ImportError as exc:
        raise HTTPException(
            status_code=400,
            detail="SVG на сервере не поддерживается — загрузите PNG",
        ) from exc
    except Exception as exc:
        logger.warning("SVG conversion failed: %s", exc)
        raise HTTPException(status_code=400, detail="Не удалось прочитать SVG") from exc


def save_tenant_stamp(tenant_id: int, file: UploadFile) -> Tuple[str, bytes]:
    raw, content_type = _read_upload(file)
    png_bytes = _to_png_bytes(raw, content_type)
    rel = f"{tenant_id}/stamp.png"
    try:
        assets_dir = tenant_assets_dir(tenant_id)
        for old in assets_dir.glob("stamp.*"):
            old.unlink(missing_ok=True)
        out_path = (assets_dir / "stamp.png").resolve()
        out_path.write_bytes(png_bytes)
        logger.info("Saved tenant stamp file: %s", out_path)
    except OSError as exc:
        logger.warning("Stamp file not written to disk (using DB only): %s", exc)
    return rel, png_bytes


def save_tenant_signature(tenant_id: int, file: UploadFile) -> Tuple[str, bytes]:
    raw, content_type = _read_upload(file)
    png_bytes = _to_png_bytes(raw, content_type)
    rel = f"{tenant_id}/signature.png"
    try:
        assets_dir = tenant_assets_dir(tenant_id)
        for old in assets_dir.glob("signature.*"):
            old.unlink(missing_ok=True)
        out_path = (assets_dir / "signature.png").resolve()
        out_path.write_bytes(png_bytes)
        logger.info("Saved tenant signature file: %s", out_path)
    except OSError as exc:
        logger.warning("Signature file not written to disk (using DB only): %s", exc)
    return rel, png_bytes


def _delete_tenant_image(file_path: Optional[str], tenant: Any = None, field: Optional[str] = None) -> None:
    path = resolve_asset_path(file_path)
    if path and path.exists():
        path.unlink(missing_ok=True)
    if tenant is not None and field:
        setattr(tenant, field, None)
    if tenant is not None and getattr(tenant, "id", None):
        cache = _cache_dir(int(tenant.id))
        if cache.exists():
            for f in cache.glob("*.png"):
                f.unlink(missing_ok=True)


def delete_tenant_stamp(stamp_file_path: Optional[str], tenant: Any = None) -> None:
    _delete_tenant_image(stamp_file_path, tenant=tenant, field="stamp_png")


def delete_tenant_signature(signature_file_path: Optional[str], tenant: Any = None) -> None:
    _delete_tenant_image(signature_file_path, tenant=tenant, field="signature_png")
