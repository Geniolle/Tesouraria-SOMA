"""
Cash Balance Service

Updates the final cash balance in GERENCIAR CAIXAS sheet.
Discovers target column dynamically from the sheet header.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class CashBalanceError(Exception):
    """Raised when cash balance update fails."""

    pass


@dataclass(frozen=True)
class HeaderColumn:
    """Represents a header column in the sheet."""

    index: int
    column_number: int
    column_letter: str
    original_name: str
    normalized_name: str


class CashBalanceService:
    """Service to update cash balance in sheet by discovering column from header."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        sheet_name: str,
        account_label: str,
        header_row: int = 1,
        row_offset: int = 1,
        verify_after_write: bool = True,
    ):
        """
        Initialize cash balance service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
            sheet_name: Sheet name (e.g., "GERENCIAR CAIXAS")
            account_label: Header text to search for (e.g., "CAIXA ECONÔMICA MONTEPIO GERAL - CC")
            header_row: Row number containing headers (1-indexed, default 1)
            row_offset: Rows below header to write balance (default 1)
            verify_after_write: Whether to verify value after writing
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.account_label = account_label
        self.header_row = header_row
        self.row_offset = row_offset
        self.verify_after_write = verify_after_write

    def inspect_target(self) -> dict:
        """
        Inspect target column without writing (read-only).

        Returns:
            Dict with header info, column details, and target cell info

        Raises:
            CashBalanceError: If header reading or column location fails
        """
        try:
            logger.info(f"Inspecting cash balance target in {self.sheet_name}...")

            # Load header columns
            header_columns = self._load_header_columns()

            logger.debug(f"Loaded {len(header_columns)} header columns")

            # Find account column
            account_column = self._find_account_column(header_columns)

            logger.info(
                f"Found account column: {account_column.column_letter} (index {account_column.index})"
            )

            # Calculate target cell
            target_row = self.header_row + self.row_offset

            label_cell = self._row_col_to_a1(self.header_row, account_column.column_number)
            target_cell = self._row_col_to_a1(target_row, account_column.column_number)

            logger.info(f"Label cell: {label_cell}, Target cell: {target_cell}")

            # Read previous value
            previous_value = self.sheets_client.get_cell(
                self.spreadsheet_id,
                self.sheet_name,
                target_row,
                account_column.column_number,
            )
            if previous_value is not None:
                previous_value = str(previous_value).strip()

            logger.info(f"Previous value in {target_cell}: {previous_value or '(empty)'}")

            return {
                "header_row": self.header_row,
                "header_name": account_column.original_name,
                "header_normalized": account_column.normalized_name,
                "header_index": account_column.index,
                "column_number": account_column.column_number,
                "column_letter": account_column.column_letter,
                "label_cell": label_cell,
                "target_cell": target_cell,
                "previous_value": previous_value,
                "written_value": None,
                "verified_value": None,
                "verified": False,
            }

        except CashBalanceError:
            raise
        except Exception as e:
            logger.error(f"Cash balance inspection failed: {e}", exc_info=True)
            raise CashBalanceError(f"Failed to inspect cash balance: {e}") from e

    def update_balance(self, closing_balance: Decimal) -> dict:
        """
        Update closing balance in the sheet.

        Args:
            closing_balance: Final balance to write (Decimal for precision)

        Returns:
            Result dictionary with update information

        Raises:
            CashBalanceError: If column not found, multiple found, or write fails
        """
        try:
            logger.info(f"Updating cash balance in {self.sheet_name}...")

            # Load header columns
            header_columns = self._load_header_columns()

            logger.debug(f"Loaded {len(header_columns)} header columns")

            # Find account column
            account_column = self._find_account_column(header_columns)

            logger.info(
                f"Found account column: {account_column.column_letter} (index {account_column.index})"
            )

            # Calculate target cell
            target_row = self.header_row + self.row_offset

            label_cell = self._row_col_to_a1(self.header_row, account_column.column_number)
            target_cell = self._row_col_to_a1(target_row, account_column.column_number)

            logger.info(f"Label cell: {label_cell}, Target cell: {target_cell}")

            # Read previous value
            previous_value = self.sheets_client.get_cell(
                self.spreadsheet_id,
                self.sheet_name,
                target_row,
                account_column.column_number,
            )
            if previous_value is not None:
                previous_value = str(previous_value).strip()

            logger.info(f"Previous value in {target_cell}: {previous_value or '(empty)'}")

            # Quantize balance to 0.01 EUR (Decimal precision)
            quantized_balance = closing_balance.quantize(Decimal("0.01"))

            # Format for display (two decimal places, comma separator)
            balance_formatted = str(quantized_balance).replace(".", ",")

            # Convert Decimal to float only at API boundary (JSON serialization)
            api_numeric_value = float(quantized_balance)

            # Write the balance as numeric value (RAW, not USER_ENTERED)
            logger.info(f"Writing balance {balance_formatted} ({quantized_balance}) to {target_cell}")
            self.sheets_client.update_cell(
                self.spreadsheet_id,
                self.sheet_name,
                target_row,
                account_column.column_number,
                value=api_numeric_value,
                value_input_option="RAW",
            )

            # Verify if requested
            verified = False
            verified_value = None

            if self.verify_after_write:
                logger.info(f"Verifying value in {target_cell}...")
                verified_value = self._verify_write(
                    target_row, account_column.column_number, closing_balance
                )
                verified = verified_value is not None
                if verified:
                    logger.info(f"Verification successful: {verified_value}")
                else:
                    raise CashBalanceError(
                        f"Verification failed: wrote {balance_formatted} but read different value"
                    )

            logger.info("Cash balance update completed successfully")

            return {
                "header_row": self.header_row,
                "header_name": account_column.original_name,
                "header_normalized": account_column.normalized_name,
                "header_index": account_column.index,
                "column_number": account_column.column_number,
                "column_letter": account_column.column_letter,
                "label_cell": label_cell,
                "target_cell": target_cell,
                "previous_value": previous_value,
                "written_value": balance_formatted,
                "verified_value": str(verified_value) if verified_value else None,
                "verified": verified,
            }

        except CashBalanceError:
            raise
        except Exception as e:
            logger.error(f"Cash balance update failed: {e}", exc_info=True)
            raise CashBalanceError(f"Failed to update cash balance: {e}") from e

    def _load_header_columns(self) -> list[HeaderColumn]:
        """
        Load and parse header row.

        Returns:
            List of HeaderColumn objects for all filled cells in header row

        Raises:
            CashBalanceError: If header row cannot be read
        """
        try:
            logger.info(f"Loading header row {self.header_row} from {self.sheet_name}...")

            # Read the header row
            header_values = self.sheets_client.get_row(
                self.spreadsheet_id,
                self.sheet_name,
                self.header_row,
            )

            logger.info(f"Read {len(header_values)} cells from header row")

            if not header_values:
                raise CashBalanceError(f"Header row {self.header_row} is empty in {self.sheet_name}")

            # Build header columns (preserve indices of filled cells)
            header_columns = []

            for index, cell_value in enumerate(header_values):
                if cell_value:  # Skip empty cells
                    cell_value_str = str(cell_value).strip()
                    if cell_value_str:  # Skip whitespace-only cells
                        column_number = index + 1  # Convert 0-based index to 1-based column number
                        column_letter = self.sheets_client._number_to_column(column_number)
                        normalized = self._normalize_text(cell_value_str)

                        header_col = HeaderColumn(
                            index=index,
                            column_number=column_number,
                            column_letter=column_letter,
                            original_name=cell_value_str,
                            normalized_name=normalized,
                        )

                        header_columns.append(header_col)

                        logger.debug(
                            f"  Column {column_letter} (index {index}, number {column_number}): {cell_value_str}"
                        )

            logger.info(f"Loaded {len(header_columns)} filled header columns")

            return header_columns

        except CashBalanceError:
            raise
        except Exception as e:
            logger.error(f"Failed to load header row: {e}", exc_info=True)
            raise CashBalanceError(f"Failed to load header row {self.header_row}: {e}") from e

    def _find_account_column(
        self,
        header_columns: list[HeaderColumn],
    ) -> HeaderColumn:
        """
        Find the column matching the account label.

        Args:
            header_columns: List of header columns to search

        Returns:
            HeaderColumn matching the account label

        Raises:
            CashBalanceError: If not found or multiple matches
        """
        normalized_label = self._normalize_text(self.account_label)
        found_columns = []

        for header_col in header_columns:
            if header_col.normalized_name == normalized_label:
                found_columns.append(header_col)
                logger.debug(
                    f"Matched account label at column {header_col.column_letter} (index {header_col.index})"
                )

        if len(found_columns) == 0:
            # Log available columns for debugging (without full values to avoid credential leaks)
            available_names = [f"{col.column_letter}:{col.original_name}" for col in header_columns[:5]]
            logger.error(f"Account label '{self.account_label}' not found in header row")
            logger.error(f"Available columns (sample): {', '.join(available_names)}")
            raise CashBalanceError(
                f"Account label '{self.account_label}' not found in {self.sheet_name} header row {self.header_row}"
            )

        if len(found_columns) > 1:
            column_refs = [f"{col.column_letter}" for col in found_columns]
            logger.error(f"Multiple account matches found at columns: {', '.join(column_refs)}")
            raise CashBalanceError(
                f"Multiple occurrences ({len(found_columns)}) of account label found in header row"
            )

        return found_columns[0]

    def _verify_write(self, row_idx: int, col_num: int, expected: Decimal) -> Optional[Decimal]:
        """
        Verify the written value by reading it back.

        Args:
            row_idx: Row number (1-indexed)
            col_num: Column number (1-indexed)
            expected: Expected value

        Returns:
            Verified Decimal value, or None if verification fails
        """
        try:
            logger.info(f"Verifying value at row {row_idx}, column {col_num}...")

            # Read the cell value
            cell_value = self.sheets_client.get_cell(
                self.spreadsheet_id,
                self.sheet_name,
                row_idx,
                col_num,
            )

            if not cell_value:
                logger.warning(f"Cell at row {row_idx}, column {col_num} is empty after write")
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

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for comparison.

        Handles:
        - Case folding
        - Unicode normalization
        - Extra spaces
        - Accents
        - Space around hyphens (any variation)

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Remove extra spaces and case-fold
        text = " ".join(text.split()).casefold()

        # Normalize all hyphen variations: "-" with any surrounding spaces to " - "
        text = re.sub(r"\s*-\s*", " - ", text)

        # Unicode normalization (NFD to decompose accents)
        normalized = unicodedata.normalize("NFD", text)

        # Remove combining marks (accents)
        text_no_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")

        # Normalize multiple spaces to single
        text_no_accents = re.sub(r"\s+", " ", text_no_accents)

        return text_no_accents

    @staticmethod
    def _row_col_to_a1(row_num: int, col_num: int) -> str:
        """
        Convert row/column numbers to A1 notation.

        Args:
            row_num: Row number (1-indexed)
            col_num: Column number (1-indexed)

        Returns:
            Cell reference (e.g., "A1", "C2")
        """
        col_letter = ""
        n = col_num
        while n > 0:
            n -= 1
            col_letter = chr(ord("A") + (n % 26)) + col_letter
            n //= 26
        return f"{col_letter}{row_num}"
