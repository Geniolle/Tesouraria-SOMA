"""
Batch update existing rows in CONTAORDEM with matching data.
Uses values().update() API instead of batchUpdate() for simplicity.
"""

import logging
from typing import Dict

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class BatchUpdater:
    """Update existing rows with matching data using values API."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        sheet_name: str = "CONTAORDEM",
    ):
        """Initialize batch updater."""
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name

    def update_rows(self, updates: Dict[int, Dict[str, str]]) -> Dict:
        """
        Update rows with matching data.

        Args:
            updates: {row_number: {column_name: value, ...}, ...}

        Returns:
            Stats dictionary
        """
        if not updates:
            return {"total": 0, "updated": 0, "errors": 0}

        stats = {"total": len(updates), "updated": 0, "errors": 0}

        # Helper to convert column name to A1 notation
        def col_to_letter(col_idx: int) -> str:
            """Convert column index to letter (1-indexed)."""
            col_letter = ""
            while col_idx > 0:
                col_idx -= 1
                col_letter = chr(ord('A') + (col_idx % 26)) + col_letter
                col_idx = col_idx // 26
            return col_letter

        # Get headers to find column indices
        headers = self.sheets_client.get_headers(self.spreadsheet_id, self.sheet_name)

        def get_col_idx(col_name: str) -> int:
            """Get column index by name."""
            for i, h in enumerate(headers):
                if col_name.upper() in str(h).upper():
                    return i + 1  # 1-indexed for A1 notation
            return None

        # Batch update each row
        for row_num, fields in updates.items():
            try:
                for field_name, value in fields.items():
                    col_idx = get_col_idx(field_name)

                    if col_idx is None:
                        logger.warning(f"Column '{field_name}' not found")
                        continue

                    if not value:
                        # Skip empty values
                        continue

                    # Build cell reference
                    col_letter = col_to_letter(col_idx)
                    cell_ref = f"{col_letter}{row_num}"

                    # Update single cell
                    try:
                        result = self.sheets_client.service.spreadsheets().values().update(
                            spreadsheetId=self.spreadsheet_id,
                            range=f"{self.sheet_name}!{cell_ref}",
                            valueInputOption="RAW",
                            body={"values": [[value]]}
                        ).execute()

                        if result.get("updatedCells", 0) > 0:
                            stats["updated"] += 1
                            logger.debug(f"Updated {cell_ref}: {value[:30]}")

                    except Exception as e:
                        logger.error(f"Failed to update {cell_ref}: {e}")
                        stats["errors"] += 1

            except Exception as e:
                logger.error(f"Error processing row {row_num}: {e}")
                stats["errors"] += 1

        logger.info(
            f"Batch update complete: {stats['updated']} cells updated, "
            f"{stats['errors']} errors"
        )
        if stats["updated"] > 0:
            self.sheets_client.mark_sheet_dirty(self.sheet_name)

        # Fail if any errors occurred
        if stats["errors"] > 0:
            raise RuntimeError(
                f"Batch update failed: {stats['errors']} error(s) out of {stats['total']} rows"
            )

        return stats
