"""Shared models for orchestration results and runtime context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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

    def get_gmail_client(self) -> GmailClient:
        """Return a shared Gmail client, creating it on first use."""
        if self.gmail_client is None:
            authenticator = GmailAuthenticator(
                client_secrets_path=self.settings.gmail.client_secrets_path,
                credentials_path=self.settings.gmail.credentials_path,
            )
            credentials = authenticator.get_credentials()
            self.gmail_client = GmailClient(credentials)
        return self.gmail_client

    def get_sheets_client(self) -> SheetsClient:
        """Return a shared Sheets client, creating it on first use."""
        if self.sheets_client is None:
            self.sheets_client = SheetsClient(
                service_account_path=Path(self.settings.sheets.service_account_path)
            )
        return self.sheets_client
