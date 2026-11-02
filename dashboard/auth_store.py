"""SQLite store for dashboard logins and sessions.

Passwords are kept only as salted scrypt hashes; session tokens only as SHA-256
digests, so a copy of the database does not grant access.
"""

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SESSION_TTL = 12 * 3600
_N, _R, _P = 2**14, 8, 1


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p)
        )
    except ValueError:
        return False
    return hmac.compare_digest(got, base64.b64decode(digest))


# Verified against when the email has no account, so timing does not reveal it.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _norm(email: str) -> str:
    return email.strip().lower()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self._conn() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "email TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, updated_at INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires_at INTEGER NOT NULL)"
            )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # One connection per call: the HTTP server is multi-threaded.
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:  # commits, or rolls back on error
                yield db
        finally:
            db.close()

    def emails(self) -> list[str]:
        with self._conn() as db:
            return [row[0] for row in db.execute("SELECT email FROM users ORDER BY email")]

    def set_password(self, email: str, password: str) -> None:
        with self._conn() as db:
            db.execute(
                "INSERT INTO users (email, pw_hash, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(email) DO UPDATE SET pw_hash = excluded.pw_hash, "
                "updated_at = excluded.updated_at",
                (_norm(email), hash_password(password), int(time.time())),
            )

    def check_password(self, email: str, password: str) -> bool:
        with self._conn() as db:
            row = db.execute(
                "SELECT pw_hash FROM users WHERE email = ?", (_norm(email),)
            ).fetchone()
        ok = verify_password(password, row[0] if row else _DUMMY_HASH)
        return ok and row is not None

    def delete_user(self, email: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM users WHERE email = ?", (_norm(email),))
            db.execute("DELETE FROM sessions WHERE email = ?", (_norm(email),))

    def create_session(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._conn() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            db.execute(
                "INSERT INTO sessions (token_hash, email, expires_at) VALUES (?, ?, ?)",
                (_token_hash(token), _norm(email), now + SESSION_TTL),
            )
        return token

    def session_email(self, token: str) -> str | None:
        with self._conn() as db:
            row = db.execute(
                "SELECT email FROM sessions WHERE token_hash = ? AND expires_at >= ?",
                (_token_hash(token), int(time.time())),
            ).fetchone()
        return row[0] if row else None

    def delete_session(self, token: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    def delete_sessions(self, email: str, keep_token: str | None = None) -> None:
        with self._conn() as db:
            db.execute(
                "DELETE FROM sessions WHERE email = ? AND token_hash != ?",
                (_norm(email), _token_hash(keep_token) if keep_token else ""),
            )
