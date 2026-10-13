"""
Metrix Auth Gateway — единая точка входа мобильного приложения.

Пользователь вводит только логин и пароль. Шлюз по отпечатку логина находит
BPM-сервер его ТРЦ, проверяет пароль на этом сервере и возвращает приложению
токены и адрес сервера. Список подключённых ТРЦ наружу не отдаётся: на любой
неуспех ответ одинаковый — «Неверный логин или пароль».

Логин вида «логин:код» направляет вход на сервер с этим кодом ТРЦ — для
сотрудников, у которых одинаковый логин в нескольких ТРЦ.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .store import Store, login_hash

INVALID = 'Неверный логин или пароль'


class Settings:
    def __init__(self):
        self.db_path = os.environ.get('GATEWAY_DB_PATH', 'gateway.sqlite3')
        self.login_secret = os.environ.get('LOGIN_HASH_SECRET', '')
        self.backend_timeout = float(os.environ.get('BACKEND_TIMEOUT', '10'))
        self.max_attempts = int(os.environ.get('LOGIN_MAX_ATTEMPTS', '10'))
        self.attempt_window = int(os.environ.get('LOGIN_ATTEMPT_WINDOW', '300'))


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access: str
    refresh: str
    base_url: str


class LoginsPush(BaseModel):
    logins: list[str] = Field(default_factory=list, max_length=200_000)


class RateLimiter:
    """Скользящее окно попыток входа по ключу (IP, отпечаток логина)."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings()
    if not settings.login_secret:
        raise RuntimeError('Задайте LOGIN_HASH_SECRET — тот же, что в BPM (AUTH_GATEWAY_LOGIN_SECRET)')

    store = Store(settings.db_path)
    limiter = RateLimiter(settings.max_attempts, settings.attempt_window)
    app = FastAPI(title='Metrix Auth Gateway', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def backend_from_key(authorization: str = Header(default='')):
        api_key = authorization.removeprefix('Bearer ').strip()
        backend = store.backend_by_key(api_key) if api_key else None
        if backend is None:
            raise HTTPException(status_code=401, detail='Неизвестный сервер')
        return backend

    @app.get('/health')
    async def health():
        return {'ok': True}

    @app.post('/api/login', response_model=LoginResponse)
    async def login(data: LoginRequest, request: Request):
        hash_value = login_hash(settings.login_secret, data.username)
        client_ip = request.client.host if request.client else 'unknown'
        if not (limiter.allow(f'ip:{client_ip}') and limiter.allow(f'login:{hash_value}')):
            raise HTTPException(status_code=429, detail='Слишком много попыток. Повторите позже.')

        username, backends = data.username.strip(), None
        if ':' in username:
            # «логин:код» — вход в конкретный ТРЦ (сотрудники Metrix с одним логином
            # во всех ТРЦ). Двоеточие в логинах Django запрещено — путаницы нет.
            username, code = username.rsplit(':', 1)
            backend = store.backend_by_code(code)
            backends = [backend] if backend and username else []
        if backends is None:
            backends = store.candidates(hash_value)

        async with httpx.AsyncClient(timeout=settings.backend_timeout, transport=transport) as client:
            for backend in backends:
                try:
                    response = await client.post(
                        f'{backend.base_url}/api/token/',
                        json={'username': username, 'password': data.password},
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code == 200:
                    tokens = response.json()
                    return LoginResponse(
                        access=tokens['access'], refresh=tokens['refresh'], base_url=backend.base_url,
                    )
        raise HTTPException(status_code=401, detail=INVALID)

    @app.put('/api/backend/logins')
    async def push_logins(data: LoginsPush, backend=Depends(backend_from_key)):
        valid = [h for h in data.logins if len(h) == 64 and all(c in '0123456789abcdef' for c in h)]
        count = store.replace_logins(backend.id, valid, datetime.now(timezone.utc).isoformat())
        return {'ok': True, 'logins': count}

    return app
