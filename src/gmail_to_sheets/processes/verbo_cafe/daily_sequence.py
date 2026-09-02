"""Backwards-compatible alias for the shared CONTAORDEM sequence service.

The implementation moved to
``src.gmail_to_sheets.services.contaordem_sequence`` because the
``DESCRIÇÃO SOMA`` ``N###`` rule is global to every ``CONTAORDEM`` writer.
"""

from __future__ import annotations

from src.gmail_to_sheets.services.contaordem_sequence import (
    ContaOrdemSequenceService as DailySequenceService,
)

__all__ = ["DailySequenceService"]
