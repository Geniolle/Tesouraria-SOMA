"""
Batch Writer Service

Optimizes writing to Google Sheets by batching multiple operations.
Prepares data in memory before writing in a single batch request.
"""

import logging
import time
from typing import Any

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

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "429" in text
            or "quota" in text
            or "rate limit" in text
            or "rate_limit" in text
            or "resource_exhausted" in text
        )

    def _with_quota_retry(self, operation, *, label: str, attempts: int = 5):
        """Retry Google Sheets quota/rate-limit failures with exponential backoff."""
        for attempt in range(attempts):
            try:
                return operation()
            except Exception as exc:
                if not self._is_quota_error(exc) or attempt == attempts - 1:
                    raise
                delay = min(2 ** attempt, 16)
                logger.warning(
                    "%s hit Google Sheets quota/rate limit; retry %s/%s in %ss",
                    label,
                    attempt + 1,
                    attempts - 1,
                    delay,
                )
                time.sleep(delay)

    def _confirm_target_ids(self, target_sheet: str, target_data: list[list]) -> None:
        """Confirm every appended ID_INTERNO exists in target before touching source status."""
        if not target_data:
            return

        headers = self.sheets_client.get_headers(self.spreadsheet_id, target_sheet)
        id_idx = next(
            (idx for idx, header in enumerate(headers) if str(header).strip().upper() == "ID_INTERNO"),
            None,
        )
        if id_idx is None:
            raise RuntimeError(f"ID_INTERNO column not found in {target_sheet}")

        expected_ids = {
            str(row[id_idx]).strip()
            for row in target_data
            if id_idx < len(row) and str(row[id_idx]).strip()
        }
        if not expected_ids:
            raise RuntimeError("Target write has no ID_INTERNO values to verify")

        range_name = self.sheets_client.get_data_range(self.spreadsheet_id, target_sheet)
        if not isinstance(range_name, str) or not range_name:
            range_name = f"{target_sheet}!A2:ZZ99999"

        result = self._with_quota_retry(
            lambda: self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute(),
            label=f"confirm {target_sheet}",
        )
        rows = result.get("values", [])
        actual_ids = {
            str(row[id_idx]).strip()
            for row in rows
            if id_idx < len(row) and str(row[id_idx]).strip()
        }
        missing = sorted(expected_ids - actual_ids)
        if missing:
            raise RuntimeError(
                f"Target verification failed in {target_sheet}; missing ID_INTERNO: {', '.join(missing)}"
            )

    def batch_write_with_updates(
        self,
        source_sheet: str,
        source_data: list[list],
        target_sheet: str,
        target_data: list[list],
        status_updates: dict[int, str] | None = None,
    ) -> dict[str, Any]:
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

            # Step 1: Append new rows to target sheet.
            # Fail immediately on target errors: source status must never advance
            # unless CONTAORDEM has been written and verified.
            if target_data:
                logger.info(f"Batch writing {len(target_data)} rows to {target_sheet}")
                self._with_quota_retry(
                    lambda: self.sheets_client.append_rows(
                        self.spreadsheet_id,
                        target_sheet,
                        target_data,
                    ),
                    label=f"append {target_sheet}",
                )
                stats["target_rows_written"] = len(target_data)
                logger.info(f"Wrote {len(target_data)} rows to {target_sheet}")

                self._confirm_target_ids(target_sheet, target_data)
                logger.info(
                    "Confirmed %s appended ID_INTERNO value(s) in %s before source update",
                    len(target_data),
                    target_sheet,
                )

            # Step 2: Update source sheet rows
            if source_data:
                try:
                    logger.info(f"Batch updating {len(source_data)} rows in {source_sheet}")
                    range_name = self.sheets_client.get_data_range(self.spreadsheet_id, source_sheet)
                    self.sheets_client.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        body={"values": source_data}
                    ).execute()
                    stats["source_rows_updated"] = len(source_data)
                    self.sheets_client.mark_sheet_dirty(source_sheet)
                    logger.info(f"Updated {len(source_data)} rows in {source_sheet}")
                except Exception as e:
                    logger.error(f"Failed to update {source_sheet}: {e}")
                    stats["errors"].append(f"Source update failed: {e}")

            # Step 3: Apply source status only after target write/verification succeeded.
            if status_updates:
                logger.info(f"Batch updating status for {len(status_updates)} rows")
                self._with_quota_retry(
                    lambda: self._batch_update_status(source_sheet, status_updates),
                    label=f"status update {source_sheet}",
                )
                stats["status_updates_applied"] = len(status_updates)
                self.sheets_client.mark_sheet_dirty(source_sheet)
                logger.info(f"Updated status for {len(status_updates)} rows")

            # Validate all operations completed successfully
            if stats["errors"]:
                error_msg = "; ".join(stats["errors"])
                raise RuntimeError(f"Batch write failed with {len(stats['errors'])} error(s): {error_msg}")

            return stats

        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            raise

    def _batch_update_status(self, sheet_name: str, status_updates: dict[int, str]) -> None:
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
