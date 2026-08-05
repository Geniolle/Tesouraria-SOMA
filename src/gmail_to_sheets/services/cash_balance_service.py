"""
Cash Balance Service

Updates the final cash balance in GERENCIAR CAIXAS sheet.
Locates the account label dynamically and writes the balance to the cell below.
"""

import logging
import unicodedata
from decimal import Decimal
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class CashBalanceError(Exception):
    """Raised when cash balance update fails."""

    pass


class CashBalanceService:
    """Service to update cash balance in GERENCIAR CAIXAS sheet."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        sheet_name: str,
        account_label: str,
        row_offset: int = 1,
        verify_after_write: bool = True,
    ):
        """
        Initialize cash balance service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
            sheet_name: Sheet name (e.g., "GERENCIAR CAIXAS")
            account_label: Text to search for (e.g., "CAIXA ECONÔMICA MONTEPIO GERAL - CC")
            row_offset: Rows to offset from label cell (e.g., 1 = cell below)
            verify_after_write: Whether to verify value after writing
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.account_label = account_label
        self.row_offset = row_offset
        self.verify_after_write = verify_after_write

    def update_balance(self, closing_balance: Decimal) -> dict:
        """
        Update closing balance in the sheet.

        Args:
            closing_balance: Final balance to write (Decimal for precision)

        Returns:
            Result dictionary with update information

        Raises:
            CashBalanceError: If label not found, multiple found, or write fails
        """
        try:
            logger.info(f"Updating cash balance in {self.sheet_name}...")

            # Load the sheet data
            range_name = f"{self.sheet_name}!A1:Z1000"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            if not rows:
                raise CashBalanceError(f"Sheet {self.sheet_name} appears to be empty")

            logger.debug(f"Loaded {len(rows)} rows from {self.sheet_name}")

            # Find the account label cell
            label_row, label_col = self._find_label_cell(rows)

            logger.info(f"Found label at row {label_row + 1}, column {label_col + 1}")

            # Calculate target cell
            target_row = label_row + self.row_offset
            target_col = label_col

            logger.info(f"Target cell for update: row {target_row + 1}, column {target_col + 1}")

            # Get cell reference (A1 notation)
            label_cell = self._row_col_to_a1(label_row, label_col)
            target_cell = self._row_col_to_a1(target_row, target_col)

            # Read previous value
            previous_value = self._get_cell_value(rows, target_row, target_col)

            # Format balance for writing (two decimal places)
            balance_formatted = f"{float(closing_balance):.2f}".replace(".", ",")

            # Write the balance
            logger.info(f"Writing balance {balance_formatted} to {target_cell}")
            self.sheets_client.update_cell(
                self.spreadsheet_id,
                self.sheet_name,
                target_row + 1,  # Convert to 1-indexed
                target_col + 1,  # Convert to 1-indexed
                balance_formatted,
            )

            # Verify if requested
            verified = False
            verified_value = None

            if self.verify_after_write:
                logger.info(f"Verifying value in {target_cell}...")
                verified_value = self._verify_write(
                    target_row, target_col, closing_balance
                )
                verified = verified_value is not None
                if verified:
                    logger.info(f"Verification successful: {verified_value}")
                else:
                    raise CashBalanceError(
                        f"Verification failed: wrote {balance_formatted} but read different value"
                    )

            logger.info(f"Cash balance update completed successfully")

            return {
                "sheet_name": self.sheet_name,
                "label_cell": label_cell,
                "target_cell": target_cell,
                "previous_value": previous_value,
                "written_value": balance_formatted,
                "verified_value": verified_value if verified else None,
                "verified": verified,
            }

        except CashBalanceError:
            raise
        except Exception as e:
            logger.error(f"Cash balance update failed: {e}", exc_info=True)
            raise CashBalanceError(f"Failed to update cash balance: {e}") from e

    def _find_label_cell(self, rows: list[list]) -> tuple[int, int]:
        """
        Find the cell containing the account label.

        Args:
            rows: Sheet data

        Returns:
            Tuple of (row_index, col_index)

        Raises:
            CashBalanceError: If not found or multiple occurrences
        """
        normalized_label = self._normalize_text(self.account_label)
        found_cells = []

        for row_idx, row in enumerate(rows):
            for col_idx, cell in enumerate(row):
                if cell and self._normalize_text(str(cell)) == normalized_label:
                    found_cells.append((row_idx, col_idx))
                    logger.debug(f"Found label at row {row_idx + 1}, col {col_idx + 1}")

        if len(found_cells) == 0:
            raise CashBalanceError(
                f"Label '{self.account_label}' not found in {self.sheet_name}"
            )

        if len(found_cells) > 1:
            raise CashBalanceError(
                f"Multiple occurrences ({len(found_cells)}) of '{self.account_label}' found in {self.sheet_name}"
            )

        return found_cells[0]

    def _verify_write(self, row_idx: int, col_idx: int, expected: Decimal) -> Optional[Decimal]:
        """
        Verify the written value by reading it back.

        Args:
            row_idx: Row index (0-based)
            col_idx: Column index (0-based)
            expected: Expected value

        Returns:
            Verified Decimal value, or None if verification fails
        """
        try:
            # Re-read the sheet
            range_name = f"{self.sheet_name}!A1:Z1000"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            cell_value = self._get_cell_value(rows, row_idx, col_idx)

            if not cell_value:
                logger.warning(f"Cell at row {row_idx + 1}, col {col_idx + 1} is empty after write")
                return None

            # Parse the value (handle both comma and dot as decimal separator)
            try:
                if isinstance(cell_value, str):
                    parsed = Decimal(cell_value.strip().replace(",", "."))
                else:
                    parsed = Decimal(str(cell_value))
            except Exception as e:
                logger.warning(f"Could not parse cell value '{cell_value}': {e}")
                return None

            # Compare with expected (allow 0.01 tolerance)
            difference = abs(parsed - expected)
            if difference <= Decimal("0.01"):
                return parsed
            else:
                logger.warning(
                    f"Value mismatch: expected {expected}, got {parsed}, difference {difference}"
                )
                return None

        except Exception as e:
            logger.error(f"Verification read failed: {e}", exc_info=True)
            return None

    def _get_cell_value(self, rows: list[list], row_idx: int, col_idx: int) -> Optional[str]:
        """
        Get cell value from rows.

        Args:
            rows: Sheet data
            row_idx: Row index (0-based)
            col_idx: Column index (0-based)

        Returns:
            Cell value or None if out of bounds
        """
        if row_idx < len(rows) and col_idx < len(rows[row_idx]):
            val = rows[row_idx][col_idx]
            return str(val).strip() if val else None
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for comparison.

        Handles:
        - Case folding
        - Unicode normalization
        - Extra spaces
        - Accents

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Remove extra spaces and case-fold
        text = " ".join(text.split()).casefold()

        # Unicode normalization (NFD to decompose accents)
        normalized = unicodedata.normalize("NFD", text)

        # Remove combining marks (accents)
        text_no_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")

        return text_no_accents

    @staticmethod
    def _row_col_to_a1(row_idx: int, col_idx: int) -> str:
        """
        Convert row/col indices to A1 notation.

        Args:
            row_idx: Row index (0-based)
            col_idx: Column index (0-based)

        Returns:
            Cell reference (e.g., "A1", "D5")
        """
        # Column number to letters
        col_letter = ""
        col_num = col_idx + 1
        while col_num > 0:
            col_num -= 1
            col_letter = chr(ord("A") + (col_num % 26)) + col_letter
            col_num //= 26

        # Row number
        row_num = row_idx + 1

        return f"{col_letter}{row_num}"
