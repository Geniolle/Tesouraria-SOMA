"""Efficient read-only projections for Google Sheets ranges."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _column_letter(index: int) -> str:
    """Convert a zero-based column index to an A1 column letter."""
    if index < 0:
        raise ValueError("Column index must be >= 0")

    value = index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _quote_sheet_name(sheet_name: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"


def read_projected_rows(
    sheets_client,
    spreadsheet_id: str,
    sheet_name: str,
    column_indices: dict[str, int],
    required_fields: Iterable[str],
    *,
    start_row: int = 2,
    end_row: int = 99999,
) -> list[tuple[int, list[Any]]]:
    """Read only the smallest contiguous column window needed by a probe.

    Returned rows are left-padded so the original zero-based column indices
    remain valid for existing validators and services.
    """
    normalized_fields = [str(field).upper().strip() for field in required_fields]
    indices: list[int] = []

    for field in normalized_fields:
        index = column_indices.get(field)
        if index is None:
            raise RuntimeError(
                f"Required column '{field}' not found in sheet '{sheet_name}'"
            )
        indices.append(index)

    if not indices:
        return []

    first_index = min(indices)
    last_index = max(indices)
    first_column = _column_letter(first_index)
    last_column = _column_letter(last_index)
    range_name = (
        f"{_quote_sheet_name(sheet_name)}!"
        f"{first_column}{start_row}:{last_column}{end_row}"
    )

    result = (
        sheets_client.service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        )
        .execute()
    )

    rows = result.get("values", [])
    projected: list[tuple[int, list[Any]]] = []

    for offset, row in enumerate(rows):
        padded_row = [None] * first_index + list(row)
        projected.append((start_row + offset, padded_row))

    return projected
