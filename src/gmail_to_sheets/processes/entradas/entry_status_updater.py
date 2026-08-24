"""
Entry Status Updater Service

Updates FINANCE column in DÍZIMOS/OFERTAS sheet after successful transfer.
Marks entries as "Transferido" to prevent re-processing.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EntryStatusUpdaterError(Exception):
    """Raised when status update fails."""
    pass


class EntryStatusUpdater:
    """Update status in DÍZIMOS/OFERTAS after transfer."""

    SOURCE_SHEET = "DÍZIMOS/OFERTAS"
    STATUS_FIELD = "FINANCE"
    STATUS_VALUE = "Transferido"

    def __init__(self, sheets_client, spreadsheet_id: str):
        """
        Initialize status updater.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.finance_column_index = self._find_finance_column()

    def _find_finance_column(self) -> Optional[int]:
        """Find FINANCE column index in DÍZIMOS/OFERTAS."""
        try:
            headers = self.sheets_client.get_headers(
                self.spreadsheet_id, self.SOURCE_SHEET
            )

            for idx, header in enumerate(headers):
                h = str(header).upper().strip()
                if h == "FINANCE":
                    logger.info(f"Found FINANCE column at index {idx}")
                    return idx

            logger.warning("FINANCE column not found in DÍZIMOS/OFERTAS")
            return None

        except Exception as e:
            logger.error(f"Failed to find FINANCE column: {e}")
            return None

    def mark_as_transferred(self, row_number: int) -> bool:
        """
        Mark entry as transferred by updating FINANCE column.

        Args:
            row_number: Row number in sheet (1-indexed)

        Returns:
            True if successful
        """
        if self.finance_column_index is None:
            logger.warning("Cannot update status - FINANCE column not found")
            return False

        try:
            # Column number is index + 1 (1-indexed for API)
            col_number = self.finance_column_index + 1

            logger.debug(f"Marking row {row_number} as transferred...")

            self.sheets_client.update_cell(
                self.spreadsheet_id,
                self.SOURCE_SHEET,
                row_number,
                col_number,
                self.STATUS_VALUE
            )

            logger.info(f"Row {row_number} marked as {self.STATUS_VALUE}")
            return True

        except Exception as e:
            logger.error(f"Failed to update status for row {row_number}: {e}")
            return False

    def mark_batch_as_transferred(self, row_numbers: list[int]) -> dict:
        """
        Mark multiple rows as transferred in batch.

        Args:
            row_numbers: List of row numbers to update

        Returns:
            Dictionary with success count and errors
        """
        if self.finance_column_index is None:
            return {
                "updated": 0,
                "failed": len(row_numbers),
                "errors": ["FINANCE column not found"]
            }

        if not row_numbers:
            return {
                "updated": 0,
                "failed": 0,
                "errors": []
            }

        updated_count = 0
        failed_count = 0
        errors = []

        for row_number in sorted(row_numbers):
            try:
                col_number = self.finance_column_index + 1

                logger.debug(f"Updating row {row_number}...")

                self.sheets_client.update_cell(
                    self.spreadsheet_id,
                    self.SOURCE_SHEET,
                    row_number,
                    col_number,
                    self.STATUS_VALUE
                )

                updated_count += 1
                logger.info(f"Row {row_number} marked as {self.STATUS_VALUE}")

            except Exception as e:
                failed_count += 1
                error_msg = f"Row {row_number}: {e}"
                errors.append(error_msg)
                logger.error(f"Failed to update row {row_number}: {e}")

        logger.info(f"Batch update completed: {updated_count} updated, {failed_count} failed")

        return {
            "updated": updated_count,
            "failed": failed_count,
            "errors": errors
        }

    @staticmethod
    def _number_to_column(col_num: int) -> str:
        """
        Convert column number to letter (1-indexed).

        Args:
            col_num: Column number (1-indexed)

        Returns:
            Column letter (A, B, ..., Z, AA, etc.)
        """
        col_letter = ""
        while col_num > 0:
            col_num -= 1
            col_letter = chr(65 + col_num % 26) + col_letter
            col_num //= 26
        return col_letter
