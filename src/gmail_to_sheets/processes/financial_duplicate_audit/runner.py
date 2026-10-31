"""Read-only Google Sheets boundary for the duplicate audit."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from .engine import audit_group, group_repeated_amounts, select_period_rows
from .models import AuditRun
from .origins import ORIGIN_SPECS

TARGET_REQUIRED = frozenset(
    {"TIPO", "IMPORTÂNCIA", "DATA MOV.", "DESCRIÇÃO", "PROCESSO", "ID_INTERNO", "DOC. SOMA"}
)


def _normalized_header(value: object) -> str:
    return str(value or "").strip().upper()


def rows_from_values(
    headers: list[object], values: list[list[Any]], required: set[str] | frozenset[str]
) -> list[tuple[int, dict[str, Any]]]:
    normalized = [_normalized_header(header) for header in headers]
    duplicates = sorted(header for header, count in Counter(normalized).items() if header and count > 1)
    if duplicates:
        raise ValueError(f"duplicate headers: {', '.join(duplicates)}")
    missing = sorted(_normalized_header(field) for field in required if _normalized_header(field) not in normalized)
    if missing:
        raise ValueError(f"missing headers: {', '.join(missing)}")
    return [
        (row_number, {header: row[index] if index < len(row) else "" for index, header in enumerate(normalized) if header})
        for row_number, row in enumerate(values, start=2)
    ]


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


class FinancialDuplicateAuditRunner:
    """Load current rows and execute the pure audit without any write method."""

    def __init__(
        self,
        sheets_client: Any,
        spreadsheet_id: str,
        *,
        verbo_cafe_spreadsheet_id: str | None = None,
        read_sheet: Callable[[str, str, frozenset[str]], list[tuple[int, dict[str, Any]]]] | None = None,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.verbo_cafe_spreadsheet_id = verbo_cafe_spreadsheet_id
        self._reader = read_sheet or self._read_sheet

    def _read_sheet(
        self, spreadsheet_id: str, sheet_name: str, required: frozenset[str]
    ) -> list[tuple[int, dict[str, Any]]]:
        headers = self.sheets_client.get_headers(spreadsheet_id, sheet_name)
        last_column = _column_letter(max(len(headers), 1))
        escaped = sheet_name.replace("'", "''")
        result = (
            self.sheets_client.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"'{escaped}'!A2:{last_column}")
            .execute()
        )
        return rows_from_values(headers, result.get("values", []), required)

    def run(self, *, year: int, month: int) -> AuditRun:
        target_rows = self._reader(self.spreadsheet_id, "CONTAORDEM", TARGET_REQUIRED)
        period_rows, invalid_dates = select_period_rows(target_rows, year=year, month=month)
        groups, invalid_amounts = group_repeated_amounts(period_rows)

        processes = sorted(
            {
                str(occurrence.row.get("PROCESSO") or "").strip().upper()
                for group in groups
                for occurrence in group.occurrences
                if str(occurrence.row.get("PROCESSO") or "").strip().upper() in ORIGIN_SPECS
            }
        )
        sources: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for process in processes:
            spec = ORIGIN_SPECS[process]
            spreadsheet_id = (
                self.spreadsheet_id
                if spec.spreadsheet == "main"
                else self.verbo_cafe_spreadsheet_id
            )
            if not spreadsheet_id:
                sources[process] = []
                continue
            sources[process] = self._reader(spreadsheet_id, spec.source_sheet, spec.required_headers)

        findings = tuple(
            finding
            for group in groups
            for finding in audit_group(group, sources)
        )
        return AuditRun(
            year=year,
            month=month,
            total_rows=len(target_rows),
            period_rows=len(period_rows),
            groups=tuple(groups),
            findings=findings,
            invalid_dates=tuple(invalid_dates),
            invalid_amounts=tuple(invalid_amounts),
            source_sheets=tuple(ORIGIN_SPECS[process].source_sheet for process in processes),
        )
