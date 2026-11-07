"""Diretória lookup in the BP SERVICE sheet: who may log in, and their profile.

Only rows with DIRETÓRIA = TRUE and an email are members. The sheet is cached
for a few minutes; if a refresh fails the last good copy keeps being used.
"""

import logging
import threading
import time
import unicodedata
from typing import Any

from googleapiclient.discovery import build

SHEET = "BP SERVICE"
log = logging.getLogger("dashboard.directory")


def _key(text: str) -> str:
    plain = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()
    return plain.strip().upper()


class DirectoryUnavailable(RuntimeError):
    pass


class Directory:
    def __init__(self, credentials: Any, spreadsheet_id: str, ttl: int = 300) -> None:
        self._creds = credentials
        self._id = spreadsheet_id
        self._ttl = ttl
        self._lock = threading.Lock()
        self._members: dict[str, dict[str, str]] | None = None
        self._loaded_at = 0.0

    def _fetch(self) -> dict[str, dict[str, str]]:
        sheets = build("sheets", "v4", credentials=self._creds, cache_discovery=False)
        rows = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=self._id, range=f"'{SHEET}'")
            .execute()
            .get("values", [])
        )
        if not rows:
            return {}
        col = {_key(h): i for i, h in enumerate(rows[0])}
        cell = lambda r, name: r[col[name]].strip() if col[name] < len(r) else ""  # noqa: E731
        members = {}
        for r in rows[1:]:
            email = cell(r, "EMAIL").lower()
            if cell(r, "DIRETORIA").upper() == "TRUE" and "@" in email:
                members[email] = {
                    "name": cell(r, "NOME"),
                    "email": email,
                    "photo": cell(r, "FOTO DO PERFIL"),
                }
        return members

    def members(self) -> dict[str, dict[str, str]]:
        with self._lock:
            if self._members is None or time.time() - self._loaded_at > self._ttl:
                try:
                    self._members = self._fetch()
                    self._loaded_at = time.time()
                except Exception as exc:
                    log.exception("BP SERVICE refresh failed")
                    if self._members is None:
                        raise DirectoryUnavailable("BP SERVICE unavailable") from exc
                    self._loaded_at = time.time()  # back off before retrying
            return self._members

    def get(self, email: str) -> dict[str, str] | None:
        return self.members().get(email.strip().lower())

    def photo(self, email: str) -> tuple[bytes, str] | None:
        """Profile photo from Drive, found by the file name stored in the sheet.

        Needs the AppSheet images folder shared with the service account.
        """
        member = self.get(email)
        name = (member or {}).get("photo", "").rsplit("/", 1)[-1]
        if not name:
            return None
        drive = build("drive", "v3", credentials=self._creds, cache_discovery=False)
        quoted = name.replace("\\", "\\\\").replace("'", "\\'")
        files = (
            drive.files()
            .list(q=f"name = '{quoted}' and trashed = false", fields="files(id,mimeType)")
            .execute()
            .get("files", [])
        )
        if not files:
            return None
        data = drive.files().get_media(fileId=files[0]["id"]).execute()
        return data, files[0]["mimeType"]
