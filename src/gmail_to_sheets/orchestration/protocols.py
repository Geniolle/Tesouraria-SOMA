"""Protocol definitions for managed processes."""

from __future__ import annotations

from typing import Protocol

from .models import PendingResult, ProcessResult


class ManagedProcess(Protocol):
    """Common interface for all scheduler-managed processes."""

    name: str
    priority: int

    def check_pending(self) -> PendingResult:
        """Return a read-only assessment of pending work."""

    def run(self) -> ProcessResult:
        """Execute the process."""
