"""Transfer service for the extrato process."""

from __future__ import annotations

import logging
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.processes.extrato.transfer_service_support import (
    build_target_row,
    format_number,
    get_cell_value,
    get_index,
    get_month_text,
    load_existing_ids,
    normalize_text,
    parse_amount,
    prepare_all_data,
    set_cell_value,
)
from src.gmail_to_sheets.services.batch_writer import BatchWriter

logger = logging.getLogger(__name__)


class TransferService:
    """Service to transfer transactions with batch operations."""

    MESES = [
        "JANEIRO",
        "FEVEREIRO",
        "MARÇO",
        "ABRIL",
        "MAIO",
        "JUNHO",
        "JULHO",
        "AGOSTO",
        "SETEMBRO",
        "OUTUBRO",
        "NOVEMBRO",
        "DEZEMBRO",
    ]

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        source_sheet: str = "T_EXTRATO",
        target_sheet: str = "CONTAORDEM",
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.target_sheet = target_sheet

        self.source_headers = self._load_headers(source_sheet)
        self.target_headers = self._load_headers(target_sheet)
        self.source_indices = self._map_columns(self.source_headers)
        self.target_indices = self._map_columns(self.target_headers)

        self._validate_columns()
        self.existing_ids = self._load_existing_ids()

    def _load_headers(self, sheet_name: str) -> list[str]:
        """Load headers from sheet."""
        try:
            headers = self.sheets_client.get_headers(self.spreadsheet_id, sheet_name)
            logger.info("Loaded %s columns from %s", len(headers), sheet_name)
            return headers
        except Exception as exc:
            logger.error("Failed to load headers from %s: %s", sheet_name, exc)
            raise

    def _map_columns(self, headers: list[str]) -> dict[str, int]:
        """Map column names to indices."""
        indices: dict[str, int] = {}
        for idx, header in enumerate(headers):
            indices[str(header).strip().upper()] = idx
        return indices

    def _validate_columns(self) -> None:
        """Validate required columns exist."""
        required_source = [
            "DATA MOV.",
            "DESCRIÇÃO",
            "TIPO",
            "IMPORTÂNCIA",
            "ID_INTERNO",
            "STATUS",
        ]
        required_target = [
            "DATA MOV.",
            "DESCRIÇÃO",
            "IMPORTÂNCIA",
            "TIPO",
            "PERÍODO",
            "PROCESSO",
            "ID_INTERNO",
        ]

        missing_source = [col for col in required_source if col.upper() not in self.source_indices]
        missing_target = [col for col in required_target if col.upper() not in self.target_indices]

        if missing_source:
            raise RuntimeError(f"Missing columns in {self.source_sheet}: {missing_source}")
        if missing_target:
            raise RuntimeError(f"Missing columns in {self.target_sheet}: {missing_target}")

        logger.info("All required columns validated")

    def _load_existing_ids(self) -> set[str]:
        """Load existing IDs from target sheet."""
        try:
            existing_ids = load_existing_ids(
                self.sheets_client,
                self.spreadsheet_id,
                self.target_sheet,
                self.target_indices,
            )
            logger.info("Loaded %s existing IDs from %s", len(existing_ids), self.target_sheet)
            return existing_ids
        except Exception as exc:
            logger.error("Failed to load existing IDs: %s", exc)
            raise

    def transfer_pending(self, source_ids: list[str] | set[str] | None = None) -> dict:
        """Transfer pending transactions with batch optimization."""
        try:
            if not source_ids:
                logger.info("No source IDs provided for transfer, skipping")
                return {
                    "transferred": 0,
                    "already_exists": 0,
                    "empty_id": 0,
                    "with_status": 0,
                    "total_processed": 0,
                }

            source_ids_set = set(self._normalize_text(id_) for id_ in source_ids)
            logger.info("Transfer limited to %s source IDs", len(source_ids_set))
            logger.info("Starting batch transfer from %s to %s", self.source_sheet, self.target_sheet)

            range_name = self.sheets_client.get_data_range(self.spreadsheet_id, self.source_sheet)
            if not isinstance(range_name, str) or not range_name:
                range_name = f"{self.source_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            source_rows = result.get("values", [])
            logger.info("Found %s rows in %s", len(source_rows), self.source_sheet)

            logger.info("Phase 1: Preparing data...")
            prepared_data = prepare_all_data(
                source_rows=source_rows,
                source_ids_set=source_ids_set,
                source_indices=self.source_indices,
                target_indices=self.target_indices,
                target_header_count=len(self.target_headers),
                existing_ids=self.existing_ids,
                meses=self.MESES,
            )

            target_rows = prepared_data["target_rows"]
            status_updates = prepared_data["status_updates"]
            stats = prepared_data["stats"]

            logger.info("Prepared: %s to transfer, %s status updates", len(target_rows), len(status_updates))

            if target_rows or status_updates:
                logger.info("Phase 2: Batch writing to sheets...")
                batch_writer = BatchWriter(self.sheets_client, self.spreadsheet_id)
                batch_result = batch_writer.batch_write_with_updates(
                    source_sheet=self.source_sheet,
                    source_data=[],
                    target_sheet=self.target_sheet,
                    target_data=target_rows,
                    status_updates=status_updates,
                )
                logger.info("Batch write result: %s", batch_result)

                if batch_result["target_rows_written"] != len(target_rows):
                    raise RuntimeError(
                        f"Incomplete write: expected {len(target_rows)} rows, got {batch_result['target_rows_written']}"
                    )
                if batch_result["status_updates_applied"] != len(status_updates or {}):
                    raise RuntimeError(
                        "Incomplete status updates: expected "
                        f"{len(status_updates or {})}, got {batch_result['status_updates_applied']}"
                    )

            logger.info(
                "Transfer completed: %s transferred, %s duplicates",
                stats["transferred"],
                stats["already_exists"],
            )
            return stats
        except Exception as exc:
            logger.error("Transfer failed: %s", exc)
            raise

    def _prepare_all_data(self, source_rows: list[list], source_ids_set: set[str] | None = None) -> dict:
        """Prepare all data for batch writing."""
        return prepare_all_data(
            source_rows=source_rows,
            source_ids_set=source_ids_set,
            source_indices=self.source_indices,
            target_indices=self.target_indices,
            target_header_count=len(self.target_headers),
            existing_ids=self.existing_ids,
            meses=self.MESES,
        )

    def _build_target_row(self, source_row: list) -> list:
        """Build a row for target sheet (CONTAORDEM)."""
        return build_target_row(
            source_row=source_row,
            source_indices=self.source_indices,
            target_indices=self.target_indices,
            target_header_count=len(self.target_headers),
            meses=self.MESES,
        )

    def _get_index(self, column_name: str, indices: dict) -> Optional[int]:
        """Get column index."""
        return get_index(column_name, indices)

    def _get_cell_value(self, row: list, column_name: str, indices: dict) -> str:
        """Get cell value by column name."""
        return get_cell_value(row, column_name, indices)

    def _set_cell_value(self, row: list, column_name: str, value: str, indices: dict) -> None:
        """Set cell value by column name."""
        set_cell_value(row, column_name, value, indices)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text."""
        return normalize_text(text)

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Parse amount with comma as decimal."""
        return parse_amount(value)

    @staticmethod
    def _format_number(value: float) -> str:
        """Format number with comma."""
        return format_number(value)

    def _get_month_text(self, data_str: str) -> str:
        """Extract month from date (DD/MM/YYYY)."""
        return get_month_text(data_str, self.MESES)
