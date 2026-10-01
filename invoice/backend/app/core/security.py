from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire_delta = timedelta(minutes=expires_minutes or settings.ADMIN_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {"sub": subject, "exp": expire, "typ": "admin"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_tenant_portal_token(tenant_id: int, trc_id: int, expires_minutes: Optional[int] = None) -> str:
    expire_delta = timedelta(minutes=expires_minutes or settings.ADMIN_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": f"tenant:{tenant_id}",
        "typ": "tenant",
        "role": "tenant",
        "tid": tenant_id,
        "trc_id": trc_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_trc_portal_token(trc_id: int, expires_minutes: Optional[int] = None) -> str:
    expire_delta = timedelta(minutes=expires_minutes or settings.ADMIN_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": f"trc:{trc_id}",
        "typ": "tenant",
        "role": "trc",
        "tid": 0,
        "trc_id": trc_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("typ") == "tenant":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def decode_tenant_portal_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("typ") != "tenant":
            return None
        trc_id = payload.get("trc_id")
        if trc_id is None:
            return None
        role = payload.get("role") or "tenant"
        raw_tid = payload.get("tid")
        tenant_id = None
        if raw_tid is not None and int(raw_tid) > 0:
            tenant_id = int(raw_tid)
        return {"tenant_id": tenant_id, "trc_id": int(trc_id), "role": role}
    except (JWTError, TypeError, ValueError):
        return None
