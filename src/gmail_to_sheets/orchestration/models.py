"""Shared models for orchestration results and runtime context."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.gmail_to_sheets.clients.drive_client import DriveClient
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.clients.sheets_client import SheetsClient


class ProcessStatus(str, Enum):
    """Execution status for a managed process."""

    SKIPPED = "SKIPPED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(slots=True)
class PendingResult:
    """Read-only result from a pending-work check."""

    has_work: bool
    count: int = 0
    reason: str = ""


@dataclass(slots=True)
class ProcessResult:
    """Result returned by a managed process execution."""

    process_name: str
    status: ProcessStatus
    processed: int = 0
    duration_seconds: float = 0.0
    error: str | None = None


@dataclass(slots=True)
class ProcessContext:
    """Shared runtime context for all managed processes."""

    settings: Any
    gmail_client: GmailClient | None = None
    sheets_client: SheetsClient | None = None
    drive_client: DriveClient | None = None
    headers_cache: dict[str, list[str]] = field(default_factory=dict)

    def get_gmail_client(self) -> GmailClient:
        """Return a shared Gmail client, creating it on first use."""
        if self.gmail_client is None:
            credentials = self._gmail_credentials()
            self.gmail_client = GmailClient(credentials)
        return self.gmail_client

    def get_drive_client(self) -> DriveClient:
        """Return a shared Drive client (reuses the Gmail OAuth account)."""
        if self.drive_client is None:
            self.drive_client = DriveClient(self._gmail_credentials())
        return self.drive_client

    def _gmail_credentials(self):
        authenticator = GmailAuthenticator(
            client_secrets_path=self.settings.gmail.client_secrets_path,
            credentials_path=self.settings.gmail.credentials_path,
        )
        return authenticator.get_credentials()

    def get_sheets_client(self) -> SheetsClient:
        """Return a shared Sheets client, creating it on first use."""
        if self.sheets_client is None:
            self.sheets_client = SheetsClient(
                service_account_path=Path(self.settings.sheets.service_account_path)
            )
        return self.sheets_client

    def get_sheet_headers(
        self,
        sheet_name: str,
        spreadsheet_id: str | None = None,
    ) -> list[str]:
        """Return cached sheet headers.

        Headers are metadata and safe to cache for the lifetime of the service.
        A service restart refreshes the cache if the spreadsheet structure changes.

        ``spreadsheet_id`` defaults to the main treasury spreadsheet; pass an
        explicit id to read headers from another spreadsheet (e.g. the Verbo
        Café source). The cache key includes the spreadsheet id so sheets with
        the same name in different spreadsheets stay isolated.
        """
        resolved_id = spreadsheet_id or self.settings.sheets.spreadsheet_id
        cache_key = f"{resolved_id}::{sheet_name}"
        if cache_key not in self.headers_cache:
            self.headers_cache[cache_key] = self.get_sheets_client().get_headers(
                resolved_id,
                sheet_name,
            )
        return list(self.headers_cache[cache_key])
