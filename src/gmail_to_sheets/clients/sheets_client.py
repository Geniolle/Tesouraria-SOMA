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

            logger.debug(f"Updated cell {range_name} with value: {value} (inputOption={value_input_option})")
            return result
        except HttpError as e:
            logger.error(f"Failed to update cell: {e}")
            raise

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
