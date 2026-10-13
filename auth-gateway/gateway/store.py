"""
Хранилище шлюза: подключённые BPM-серверы и отпечатки логинов их пользователей.

Логины не хранятся: только HMAC-SHA256(LOGIN_HASH_SECRET, логин). Тот же
секрет знают BPM-серверы — они присылают уже готовые отпечатки.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS backends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL UNIQUE,
    api_key_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    logins_synced_at TEXT
);
CREATE TABLE IF NOT EXISTS logins (
    login_hash TEXT NOT NULL,
    backend_id INTEGER NOT NULL REFERENCES backends(id) ON DELETE CASCADE,
    PRIMARY KEY (login_hash, backend_id)
);
CREATE INDEX IF NOT EXISTS logins_by_hash ON logins(login_hash);
"""


def normalize_login(login: str) -> str:
    return (login or '').strip().lower()


def login_hash(secret: str, login: str) -> str:
    return hmac.new(secret.encode(), normalize_login(login).encode(), hashlib.sha256).hexdigest()


def normalize_code(code: str | None) -> str | None:
    code = (code or '').strip().lower()
    return code or None


def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


@dataclass
class Backend:
    id: int
    name: str
    base_url: str


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute('PRAGMA table_info(backends)')}
            if 'code' not in columns:
                conn.execute('ALTER TABLE backends ADD COLUMN code TEXT')
                conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS backends_code ON backends(code)')

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── управление серверами (CLI) ───────────────────────────────────────

    def add_backend(self, name: str, base_url: str, code: str | None = None) -> str:
        """Регистрирует BPM-сервер и возвращает его API-ключ (показывается один раз)."""
        api_key = secrets.token_urlsafe(32)
        with self._conn() as conn:
            conn.execute(
                'INSERT INTO backends (name, base_url, api_key_hash, code) VALUES (?, ?, ?, ?)',
                (name, base_url.rstrip('/'), _key_hash(api_key), normalize_code(code)),
            )
        return api_key

    def set_code(self, base_url: str, code: str | None) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                'UPDATE backends SET code = ? WHERE base_url = ?',
                (normalize_code(code), base_url.rstrip('/')),
            )
            return cur.rowcount > 0

    def backend_by_code(self, code: str) -> Backend | None:
        with self._conn() as conn:
            row = conn.execute(
                'SELECT id, name, base_url FROM backends WHERE code = ? AND is_active = 1',
                (normalize_code(code),),
            ).fetchone()
        return Backend(*row) if row else None

    def set_active(self, base_url: str, active: bool) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                'UPDATE backends SET is_active = ? WHERE base_url = ?',
                (int(active), base_url.rstrip('/')),
            )
            return cur.rowcount > 0

    def list_backends(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT b.id, b.name, b.base_url, b.is_active, b.logins_synced_at, COUNT(l.login_hash), b.code '
                'FROM backends b LEFT JOIN logins l ON l.backend_id = b.id GROUP BY b.id ORDER BY b.id'
            ).fetchall()
        keys = ('id', 'name', 'base_url', 'is_active', 'logins_synced_at', 'logins', 'code')
        return [dict(zip(keys, row)) for row in rows]

    # ── API ──────────────────────────────────────────────────────────────

    def backend_by_key(self, api_key: str) -> Backend | None:
        with self._conn() as conn:
            row = conn.execute(
                'SELECT id, name, base_url FROM backends WHERE api_key_hash = ? AND is_active = 1',
                (_key_hash(api_key),),
            ).fetchone()
        return Backend(*row) if row else None

    def replace_logins(self, backend_id: int, hashes: list[str], synced_at: str) -> int:
        unique = sorted(set(hashes))
        with self._conn() as conn:
            conn.execute('DELETE FROM logins WHERE backend_id = ?', (backend_id,))
            conn.executemany(
                'INSERT INTO logins (login_hash, backend_id) VALUES (?, ?)',
                [(h, backend_id) for h in unique],
            )
            conn.execute('UPDATE backends SET logins_synced_at = ? WHERE id = ?', (synced_at, backend_id))
        return len(unique)

    def candidates(self, hash_value: str) -> list[Backend]:
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT b.id, b.name, b.base_url FROM logins l JOIN backends b ON b.id = l.backend_id '
                'WHERE l.login_hash = ? AND b.is_active = 1 ORDER BY b.id',
                (hash_value,),
            ).fetchall()
        return [Backend(*row) for row in rows]
