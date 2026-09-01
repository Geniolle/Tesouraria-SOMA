"""Integrated transfer + matching service."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.processes.extrato.transfer_matching_layout import TransferMatchingLayout
from src.gmail_to_sheets.processes.extrato.transfer_matching_row_builder import (
    TransferMatchingRowBuilder,
)
from src.gmail_to_sheets.services.batch_updater import BatchUpdater
from src.gmail_to_sheets.services.batch_writer import BatchWriter

logger = logging.getLogger(__name__)


class TransferMatchingService:
    """Coordinates transfer, matching and batch updates."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        source_sheet: str = "T_EXTRATO",
        target_sheet: str = "CONTAORDEM",
        reference_sheet: str = "CONSTANTES",
    ) -> None:
        self.layout = TransferMatchingLayout(
            sheets_client=sheets_client,
            spreadsheet_id=spreadsheet_id,
            source_sheet=source_sheet,
            target_sheet=target_sheet,
            reference_sheet=reference_sheet,
        )
        self.layout.load()
        self.row_builder = TransferMatchingRowBuilder(self.layout)

        self.sheets_client = self.layout.sheets_client
        self.spreadsheet_id = self.layout.spreadsheet_id
        self.source_sheet = self.layout.source_sheet
        self.target_sheet = self.layout.target_sheet
        self.reference_sheet = self.layout.reference_sheet
        self.source_headers = self.layout.source_headers
        self.target_headers = self.layout.target_headers
        self.ref_headers = self.layout.ref_headers
        self.source_indices = self.layout.source_indices
        self.target_indices = self.layout.target_indices
        self.ref_indices = self.layout.ref_indices
        self.ref_data = self.layout.ref_data
        self.existing_ids = self.layout.existing_ids
        self.existing_doc_soma = self.layout.existing_doc_soma
        self.existing_plano_conta = self.layout.existing_plano_conta
        self._sheet_ids_cache = self.layout.sheet_ids_cache
        self._seq_state = self.layout.seq_state

    def process_with_matching(self, source_ids: list[str] | set[str] | None = None) -> dict:
        if not source_ids:
            logger.info("No source IDs provided for processing, skipping")
            return {
                "transferred": 0,
                "already_exists": 0,
                "updated": 0,
                "skipped_resolved": 0,
                "empty_id": 0,
                "with_status": 0,
                "matched": 0,
                "no_match": 0,
                "total_processed": 0,
            }

        source_ids_set = set(self.layout.normalize_text(id_) for id_ in source_ids)
        logger.info(f"Processing limited to {len(source_ids_set)} source IDs")

        range_name = self.sheets_client.get_data_range(self.spreadsheet_id, self.source_sheet)
        if not isinstance(range_name, str) or not range_name:
            range_name = f"{self.source_sheet}!A2:Z99999"
        result = self.sheets_client.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
        ).execute()
        source_rows = result.get("values", [])

        prepared = self.row_builder.prepare_with_matching(source_rows, source_ids_set)
        target_rows = prepared["target_rows"]
        status_updates = prepared["status_updates"]
        update_rows = prepared["update_rows"]
        stats = prepared["stats"]

        if target_rows or status_updates:
            batch_writer = BatchWriter(self.sheets_client, self.spreadsheet_id)
            batch_result = batch_writer.batch_write_with_updates(
                source_sheet=self.source_sheet,
                source_data=[],
                target_sheet=self.target_sheet,
                target_data=target_rows,
                status_updates=status_updates,
            )

            if batch_result["target_rows_written"] != len(target_rows):
                raise RuntimeError(
                    f"Incomplete write: expected {len(target_rows)} rows, got {batch_result['target_rows_written']}"
                )
            if batch_result["status_updates_applied"] != len(status_updates or {}):
                raise RuntimeError(
                    f"Incomplete status updates: expected {len(status_updates or {})}, got {batch_result['status_updates_applied']}"
                )

        if update_rows:
            updater = BatchUpdater(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.spreadsheet_id,
                sheet_name=self.target_sheet,
            )
            update_result = updater.update_rows(update_rows)
            logger.info(
                f"Update result: {update_result['updated']} cells updated, "
                f"{update_result['errors']} errors"
            )

        if self.target_sheet.strip().casefold() == "contaordem":
            self.sheets_client.ensure_contaordem_sorted(
                self.spreadsheet_id
            )

        return stats

    def _prepare_with_matching(self, source_rows: list[list], source_ids_set: set[str] | None = None) -> dict:
        return self.row_builder.prepare_with_matching(source_rows, source_ids_set)

    def _find_match(self, source_row: list) -> Optional[dict]:
        return self.row_builder.find_match(source_row)

    def _build_target_row(self, source_row: list) -> list:
        return self.row_builder.build_target_row(source_row)

    def _generate_sequential_description(self, data_mov: str, desc_soma_base: str) -> str:
        return self.row_builder.generate_sequential_description(data_mov, desc_soma_base)

    def _enrich_with_match(
        self,
        target_row: list[Any],
        match: dict[str, Any],
        source_row: list[Any] | None = None,
    ) -> list[Any]:
        return self.row_builder.enrich_with_match(target_row, match, source_row)

    def _batch_update_existing(self, update_rows: dict) -> None:
        self.row_builder.batch_update_existing(update_rows)

    def _get_sheet_id(self, sheet_name: str) -> int:
        return self.layout.get_sheet_id(sheet_name)

    def _get_index(self, column_name: str, indices: dict) -> Optional[int]:
        return self.layout.get_index(column_name, indices)

    def _get_cell_value(self, row: list, column_name: str, indices: dict) -> str:
        return self.layout.get_cell_value(row, column_name, indices)

    def _set_cell_value(self, row: list, column_name: str, value: str, indices: dict) -> None:
        self.layout.set_cell_value(row, column_name, value, indices)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return TransferMatchingLayout.normalize_text(text)

    @staticmethod
    def _parse_amount(value: str) -> float:
        return TransferMatchingLayout.parse_amount(value)

    @staticmethod
    def _format_number(value: float) -> str:
        return TransferMatchingLayout.format_number(value)

    @staticmethod
    def _get_month_text(data_str: str) -> str:
        return TransferMatchingLayout.get_month_text(data_str)
