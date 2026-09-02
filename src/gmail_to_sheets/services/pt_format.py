"""Shared pt-PT formatting helpers used when writing to ``CONTAORDEM``.

These mirror the ``toNumber_`` / month-name behaviour of the legacy Apps
Script and the conventions used by ``Saidas``, ``DizimosOfertas`` and
``VerboCafe``. Kept here (not inside a process package) because the rules
are global to every CONTAORDEM writer.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

_MESES = [
    "JANEIRO",
    "FEVEREIRO",
    "MARÇO",
    "ABRIL",
    "MAIO",
    "JUNHO",
    "JULHO",
    "AGOSTO",
    "SETEMBRO",
    "OUTUBRO",
    "NOVEMBRO",
    "DEZEMBRO",
]

_WHITESPACE = re.compile(r"\s+")


def strip_accents_upper(value: object) -> str:
    """Normalize text for accent- and case-insensitive comparisons.

    ``"Concluído"`` and ``"CONCLUIDO"`` both become ``"CONCLUIDO"``.
    """
    text = "" if value is None else str(value)
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )
    return _WHITESPACE.sub(" ", without_marks).strip().upper()


def to_number(value: object) -> float:
    """Parse a pt-PT money string into a float.

    Removes thousands separators and converts the decimal comma, matching the
    Apps Script ``toNumber_`` helper. Returns ``0.0`` on failure.
    """
    if isinstance(value, (int, float)):
        return float(value)

    text = ("" if value is None else str(value)).strip()
    if not text:
        return 0.0

    text = _WHITESPACE.sub("", text).replace("\xa0", "").replace("€", "")
    if "," in text:
        # pt-PT: dots are thousands separators, comma is the decimal point.
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def format_amount_pt(value: object) -> str:
    """Format a value as ``"1234,56"`` for the CONTAORDEM ``IMPORTÂNCIA`` cell."""
    number = to_number(value)
    return f"{number:.2f}".replace(".", ",")


def parse_date(value: object) -> datetime | None:
    """Parse a source ``DATA`` value into a ``datetime``.

    Accepts ``datetime``, Google Sheets serial numbers, and ``dd/MM/yyyy`` or
    other common string formats.
    """
    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        # Google Sheets serial date (days since 1899-12-30).
        try:
            return datetime(1899, 12, 30) + timedelta(days=int(value))
        except (ValueError, OverflowError):
            return None

    text = ("" if value is None else str(value)).strip()
    if not text:
        return None

    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_date_ddmmyyyy(value: object) -> str | None:
    """Return the source ``DATA`` value normalized to ``dd/MM/yyyy``."""
    parsed = parse_date(value)
    if parsed is None:
        return None
    return parsed.strftime("%d/%m/%Y")


def month_name_pt(data_ddmmyyyy: str | None) -> str:
    """Return the Portuguese uppercase month name for a ``dd/MM/yyyy`` string."""
    if not data_ddmmyyyy:
        return ""
    try:
        month = datetime.strptime(str(data_ddmmyyyy).strip(), "%d/%m/%Y").month
    except ValueError:
        return ""
    return _MESES[month - 1]
