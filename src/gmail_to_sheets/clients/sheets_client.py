"""
Google Sheets API Client

Handles authentication and operations with Google Sheets.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class SheetsClient:
    """Client for Google Sheets API operations."""

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, service_account_path: Path):
        """
        Initialize Sheets client.

        Args:
            service_account_path: Path to service account JSON file
        """
        self.service_account_path = Path(service_account_path)
        self.credentials = self._load_credentials()
        self.service = build("sheets", "v4", credentials=self.credentials)
        self._dirty_sheets: set[str] = set()

    @staticmethod
    def _quote_sheet_name(sheet_name: str) -> str:
        """
        Quote and escape sheet name for use in A1 ranges.

        Handles sheet names with spaces and apostrophes.

        Args:
            sheet_name: Original sheet name

        Returns:
            Properly escaped sheet name (e.g., 'Sheet Name', 'Caixa d''Água')
        """
        escaped = sheet_name.replace("'", "''")
        return f"'{escaped}'"

    def _load_credentials(self) -> Credentials:
        """
        Load service account credentials.

        Returns:
            Service account credentials

        Raises:
            FileNotFoundError: If service account file not found
        """
        if not self.service_account_path.exists():
            raise FileNotFoundError(
                f"Service account not found: {self.service_account_path}"
            )

        try:
            credentials = Credentials.from_service_account_file(
                str(self.service_account_path), scopes=self.SCOPES
            )
            logger.info(f"Loaded service account credentials from {self.service_account_path}")
            return credentials
        except Exception as e:
            raise RuntimeError(f"Failed to load service account: {e}") from e

    def get_sheet_id(
        self, spreadsheet_id: str, sheet_name: str
    ) -> Optional[int]:
        """
        Get sheet ID by name.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name to find

        Returns:
            Sheet ID if found, None otherwise
        """
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()

            sheets = spreadsheet.get("sheets", [])
            for sheet in sheets:
                if sheet["properties"]["title"] == sheet_name:
                    return sheet["properties"]["sheetId"]

            logger.warning(f"Sheet '{sheet_name}' not found")
            return None
        except HttpError as e:
            logger.error(f"Failed to get sheet: {e}")
            raise

    def get_headers(
        self, spreadsheet_id: str, sheet_name: str
    ) -> list[str]:
        """
        Get header row from sheet.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name

        Returns:
            List of header names

        Raises:
            HttpError: If API call fails
        """
        try:
            quoted_sheet = self._quote_sheet_name(sheet_name)
            range_name = f"{quoted_sheet}!1:1"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
            ).execute()

            values = result.get("values", [])
            if values:
                return values[0]
            return []
        except HttpError as e:
            logger.error(f"Failed to get headers: {e}")
            raise

    def get_data_range(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        start_row: int = 2,
        end_row: int = 99999,
    ) -> str:
        """Build a data range that adapts to the current header width."""
        headers = self.get_headers(spreadsheet_id, sheet_name)
        last_col = self._number_to_column(max(len(headers), 1))
        quoted_sheet = self._quote_sheet_name(sheet_name)
        return f"{quoted_sheet}!A{start_row}:{last_col}{end_row}"

    def get_row(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
    ) -> list[Any]:
        """
        Get a single row from sheet.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name
            row: Row number (1-indexed)

        Returns:
            List of values in the row

        Raises:
            HttpError: If API call fails
        """
        try:
            quoted_sheet = self._quote_sheet_name(sheet_name)
            range_name = f"{quoted_sheet}!{row}:{row}"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
            ).execute()

            values = result.get("values", [])
            if values:
                return values[0]
            return []
        except HttpError as e:
            logger.error(f"Failed to get row {row}: {e}")
            raise

    def get_cell(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
        column: int,
    ) -> Any:
        """
        Get a single cell value from sheet.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name
            row: Row number (1-indexed)
            column: Column number (1-indexed)

        Returns:
            Cell value, or None if empty

        Raises:
            HttpError: If API call fails
        """
        try:
            quoted_sheet = self._quote_sheet_name(sheet_name)
            col_letter = self._number_to_column(column)
            range_name = f"{quoted_sheet}!{col_letter}{row}"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
            ).execute()

            values = result.get("values", [])
            if values and values[0]:
                return values[0][0]
            return None
        except HttpError as e:
            logger.error(f"Failed to get cell {row},{column}: {e}")
            raise

    def append_rows(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        rows: list[list[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> dict[str, Any]:
        """
        Append rows to sheet.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name
            rows: List of rows to append (each row is a list of values)
            value_input_option: How to interpret input (USER_ENTERED or RAW)

        Returns:
            API response

        Raises:
            HttpError: If API call fails
        """
        try:
            range_name = f"{sheet_name}"
            body = {
                "values": rows
            }

            result = self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body,
            ).execute()

            logger.info(
                f"Appended {len(rows)} rows to {sheet_name}: "
                f"{result.get('updates', {}).get('updatedRows', 0)} rows updated"
            )
            if rows:
                self.mark_sheet_dirty(sheet_name)

            return result
        except HttpError as e:
            logger.error(f"Failed to append rows: {e}")
            raise

    def get_last_row(
        self, spreadsheet_id: str, sheet_name: str
    ) -> int:
        """
        Get the last row number with data.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name

        Returns:
            Last row number (1-indexed)
        """
        try:
            range_name = f"{sheet_name}!A:A"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
            ).execute()

            values = result.get("values", [])
            return len(values)
        except HttpError as e:
            logger.error(f"Failed to get last row: {e}")
            raise

    def update_cell(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
        column: int,
        value: Any,
        value_input_option: str = "USER_ENTERED",
    ) -> dict[str, Any]:
        """
        Update a single cell.

        Args:
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name
            row: Row number (1-indexed)
            column: Column number (1-indexed)
            value: Value to set
            value_input_option: How to interpret input (USER_ENTERED or RAW)

        Returns:
            API response
        """
        try:
            quoted_sheet = self._quote_sheet_name(sheet_name)
            col_letter = self._number_to_column(column)
            range_name = f"{quoted_sheet}!{col_letter}{row}"

            body = {
                "values": [[value]]
            }

            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body,
            ).execute()

            logger.debug(
                f"Updated cell {range_name} with value: {value} "
                f"(inputOption={value_input_option})"
            )
            self.mark_sheet_dirty(sheet_name)
            return result
        except HttpError as e:
            logger.error(f"Failed to update cell: {e}")
            raise

    @staticmethod
    def _normalize_sheet_key(sheet_name: str) -> str:
        """Normalize a sheet name for internal dirty-state tracking."""
        return str(sheet_name or "").strip().casefold()

    def mark_sheet_dirty(self, sheet_name: str) -> None:
        """Mark a sheet as changed and requiring post-write housekeeping."""
        if not hasattr(self, "_dirty_sheets"):
            self._dirty_sheets = set()
        key = self._normalize_sheet_key(sheet_name)
        if key:
            self._dirty_sheets.add(key)

    def is_sheet_dirty(self, sheet_name: str) -> bool:
        """Return whether a sheet was changed through this client."""
        if not hasattr(self, "_dirty_sheets"):
            self._dirty_sheets = set()
        return self._normalize_sheet_key(sheet_name) in self._dirty_sheets

    def sort_sheet_by_column(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        column_name: str,
        *,
        descending: bool = True,
        header_rows: int = 1,
    ) -> dict[str, Any]:
        """Sort an entire sheet by a named column.

        The sort is strict: a missing column or sheet raises instead of
        silently leaving the sheet in an unknown order.
        """
        headers = self.get_headers(spreadsheet_id, sheet_name)
        normalized_column = str(column_name).strip().casefold()
        column_index = next(
            (
                index
                for index, header in enumerate(headers)
                if str(header).strip().casefold() == normalized_column
            ),
            None,
        )
        if column_index is None:
            raise RuntimeError(
                f"Column '{column_name}' not found in sheet '{sheet_name}'"
            )

        sheet_id = self.get_sheet_id(spreadsheet_id, sheet_name)
        if sheet_id is None:
            raise RuntimeError(f"Sheet '{sheet_name}' not found")

        last_row = self.get_last_row(spreadsheet_id, sheet_name)
        if last_row <= header_rows:
            self._dirty_sheets.discard(
                self._normalize_sheet_key(sheet_name)
            )
            return {
                "sorted": False,
                "sheet": sheet_name,
                "column": column_name,
                "rows": 0,
            }

        request = {
            "sortRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_rows,
                    "endRowIndex": last_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": max(len(headers), 1),
                },
                "sortSpecs": [
                    {
                        "dimensionIndex": column_index,
                        "sortOrder": (
                            "DESCENDING" if descending else "ASCENDING"
                        ),
                    }
                ],
            }
        }
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [request]},
        ).execute()

        self._dirty_sheets.discard(
            self._normalize_sheet_key(sheet_name)
        )
        logger.info(
            "Sorted %s by %s (%s)",
            sheet_name,
            column_name,
            "descending" if descending else "ascending",
        )
        return {
            "sorted": True,
            "sheet": sheet_name,
            "column": column_name,
            "rows": max(last_row - header_rows, 0),
        }

    def sort_contaordem_by_data_mov(
        self,
        spreadsheet_id: str,
    ) -> dict[str, Any]:
        """Sort CONTAORDEM by DATA MOV. descending."""
        return self.sort_sheet_by_column(
            spreadsheet_id,
            "CONTAORDEM",
            "DATA MOV.",
            descending=True,
        )

    def ensure_contaordem_sorted(
        self,
        spreadsheet_id: str,
    ) -> dict[str, Any]:
        """Sort CONTAORDEM only when this client changed it."""
        if not self.is_sheet_dirty("CONTAORDEM"):
            return {
                "sorted": False,
                "sheet": "CONTAORDEM",
                "column": "DATA MOV.",
                "rows": 0,
                "reason": "not-dirty",
            }
        return self.sort_contaordem_by_data_mov(spreadsheet_id)

    @staticmethod
    def _number_to_column(col_num: int) -> str:
        """
        Convert column number to letter (1=A, 2=B, ..., 27=AA).

        Args:
            col_num: Column number (1-indexed)

        Returns:
            Column letter(s)
        """
        col_letter = ""
        while col_num > 0:
            col_num -= 1
            col_letter = chr(65 + col_num % 26) + col_letter
            col_num //= 26
        return col_letter
