"""Backwards-compatible re-export of the shared pt-PT formatting helpers.

The implementation moved to
``src.gmail_to_sheets.services.pt_format`` because the rules are global to
every ``CONTAORDEM`` writer, not specific to Verbo Café. Existing
``from ._format import ...`` call sites keep working.
"""

from __future__ import annotations

from src.gmail_to_sheets.services.pt_format import (
    format_amount_pt,
    format_date_ddmmyyyy,
    month_name_pt,
    parse_date,
    strip_accents_upper,
    to_number,
)

__all__ = [
    "format_amount_pt",
    "format_date_ddmmyyyy",
    "month_name_pt",
    "parse_date",
    "strip_accents_upper",
    "to_number",
]
