"""
Batch Writer Service

Optimizes writing to Google Sheets by batching multiple operations.
Prepares data in memory before writing in a single batch request.
"""

import logging
from typing import Optional, List, Dict, Any

from src.gmail_to_sheets.clients.sheets_client import SheetsClient


logger = logging.getLogger(__name__)


class BatchWriter:
    """Service to write data to sheets in optimized batches."""

    def __init__(self, sheets_client: SheetsClient, spreadsheet_id: str):
        """
        Initialize batch writer.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id

    def batch_write_with_updates(
        self,
        source_sheet: str,
        source_data: list[list],
        target_sheet: str,
        target_data: list[list],
        status_updates: Dict[int, str] = None,
    ) -> dict:
        """
        Write data to both source and target sheets in optimized batches.

        Args:
            source_sheet: Source sheet name (e.g., T_EXTRATO)
            source_data: Data to write/update in source sheet
            target_sheet: Target sheet name (e.g., CONTAORDEM)
            target_data: Data to append to target sheet
            status_updates: Map of {row_number: status_value} for source sheet

        Returns:
            Statistics dictionary
        """
        try:
            stats = {
                "target_rows_written": 0,
                "source_rows_updated": 0,
                "status_updates_applied": 0,
                "errors": []
            }

            # Step 1: Append new rows to target sheet
            if target_data:
                try:
                    logger.info(f"Batch writing {len(target_data)} rows to {target_sheet}")
                    self.sheets_client.append_rows(
                        self.spreadsheet_id,
                        target_sheet,
                        target_data
                    )
                    stats["target_rows_written"] = len(target_data)
                    logger.info(f"Wrote {len(target_data)} rows to {target_sheet}")
                except Exception as e:
                    logger.error(f"Failed to write to {target_sheet}: {e}")
                    stats["errors"].append(f"Target write failed: {e}")

            # Step 2: Update source sheet rows
            if source_data:
                try:
                    logger.info(f"Batch updating {len(source_data)} rows in {source_sheet}")
                    range_name = f"{source_sheet}!A2:Z99999"
                    self.sheets_client.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        body={"values": source_data}
                    ).execute()
                    stats["source_rows_updated"] = len(source_data)
                    logger.info(f"Updated {len(source_data)} rows in {source_sheet}")
                except Exception as e:
                    logger.error(f"Failed to update {source_sheet}: {e}")
                    stats["errors"].append(f"Source update failed: {e}")

            # Step 3: Apply status updates as batch
            if status_updates:
                try:
                    logger.info(f"Batch updating status for {len(status_updates)} rows")
                    self._batch_update_status(source_sheet, status_updates)
                    stats["status_updates_applied"] = len(status_updates)
                    logger.info(f"Updated status for {len(status_updates)} rows")
                except Exception as e:
                    logger.error(f"Failed to update status: {e}")
                    stats["errors"].append(f"Status update failed: {e}")

            return stats

        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            raise

    def _batch_update_status(self, sheet_name: str, status_updates: Dict[int, str]) -> None:
        """
        Batch update STATUS column.

        Args:
            sheet_name: Sheet to update
            status_updates: Map of {row_number: status_value}
        """
        try:
            # Get headers to find STATUS column
            headers = self.sheets_client.get_headers(self.spreadsheet_id, sheet_name)
            status_col_idx = None

            for idx, header in enumerate(headers):
                if "STATUS" in str(header).upper():
                    status_col_idx = idx
                    break

            if status_col_idx is None:
                logger.warning(f"STATUS column not found in {sheet_name}")
                return

            # Build batch update request
            requests = []
            col_letter = self._number_to_column(status_col_idx + 1)

            for row_number, status_value in status_updates.items():
                range_name = f"{sheet_name}!{col_letter}{row_number}"
                requests.append({
                    "range": range_name,
                    "majorDimension": "ROWS",
                    "values": [[status_value]]
                })

            # Execute batch update
            if requests:
                body = {"data": requests, "valueInputOption": "USER_ENTERED"}
                self.sheets_client.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=body
                ).execute()
                logger.info(f"Batch updated {len(requests)} status fields")

        except Exception as e:
            logger.warning(f"Failed to batch update status: {e}")
            raise

    @staticmethod
    def _number_to_column(col_num: int) -> str:
        """Convert column number to letter (1=A, 2=B, etc)."""
        col_letter = ""
        while col_num > 0:
            col_num -= 1
            col_letter = chr(65 + col_num % 26) + col_letter
            col_num //= 26
        return col_letter
