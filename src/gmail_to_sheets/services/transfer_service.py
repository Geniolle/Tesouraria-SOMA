"""
Transfer Service (Batch Optimized)

Transfers transactions from T_EXTRATO to CONTAORDEM with optimized batch operations.
Prepares all data in memory before writing in a single batch request.
"""

import logging
import unicodedata
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.services.batch_writer import BatchWriter

logger = logging.getLogger(__name__)


class TransferService:
    """Service to transfer transactions with batch operations."""

    MESES = [
        "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
        "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"
    ]

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        source_sheet: str = "T_EXTRATO",
        target_sheet: str = "CONTAORDEM",
    ):
        """Initialize transfer service."""
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
            logger.info(f"Loaded {len(headers)} columns from {sheet_name}")
            return headers
        except Exception as e:
            logger.error(f"Failed to load headers from {sheet_name}: {e}")
            raise

    def _map_columns(self, headers: list[str]) -> dict[str, int]:
        """Map column names to indices."""
        indices = {}
        for idx, header in enumerate(headers):
            key = str(header).strip().upper()
            indices[key] = idx
        return indices

    def _validate_columns(self) -> None:
        """Validate required columns exist."""
        required_source = ["DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "ID_INTERNO", "STATUS"]
        required_target = ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "PERÍODO", "PROCESSO", "ID_INTERNO"]

        missing_source = [col for col in required_source if col.upper() not in self.source_indices]
        missing_target = [col for col in required_target if col.upper() not in self.target_indices]

        if missing_source:
            raise RuntimeError(f"Missing columns in {self.source_sheet}: {missing_source}")
        if missing_target:
            raise RuntimeError(f"Missing columns in {self.target_sheet}: {missing_target}")

        logger.info("✓ All required columns validated")

    def _load_existing_ids(self) -> set:
        """Load existing IDs from target sheet."""
        try:
            range_name = f"{self.target_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            id_idx = self.target_indices.get("ID_INTERNO")

            if id_idx is None:
                return set()

            existing_ids = set()
            for row in rows:
                if id_idx < len(row) and row[id_idx]:
                    id_val = self._normalize_text(str(row[id_idx]))
                    existing_ids.add(id_val)

            logger.info(f"Loaded {len(existing_ids)} existing IDs from {self.target_sheet}")
            return existing_ids

        except Exception as e:
            logger.error(f"Failed to load existing IDs: {e}")
            raise

    def transfer_pending(self, source_ids: list[str] | set[str] | None = None) -> dict:
        """
        Transfer pending transactions with batch optimization.

        Args:
            source_ids: List/set of ID_INTERNO values to transfer. If empty or None,
                       returns zero statistics without processing.

        Returns:
            Transfer statistics
        """
        try:
            # If no source IDs provided, return zero statistics
            if not source_ids:
                logger.info("No source IDs provided for transfer, skipping")
                return {
                    "transferred": 0,
                    "already_exists": 0,
                    "empty_id": 0,
                    "with_status": 0,
                    "total_processed": 0,
                }

            # Normalize to set for faster lookups
            source_ids_set = set(self._normalize_text(id_) for id_ in source_ids)
            logger.info(f"Transfer limited to {len(source_ids_set)} source IDs")

            logger.info(f"Starting batch transfer from {self.source_sheet} to {self.target_sheet}")

            # Load source data
            range_name = f"{self.source_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            source_rows = result.get("values", [])
            logger.info(f"Found {len(source_rows)} rows in {self.source_sheet}")

            # Phase 1: Prepare all data in memory
            logger.info("Phase 1: Preparing data...")
            prepared_data = self._prepare_all_data(source_rows, source_ids_set)

            target_rows = prepared_data["target_rows"]
            status_updates = prepared_data["status_updates"]
            stats = prepared_data["stats"]

            logger.info(f"Prepared: {len(target_rows)} to transfer, {len(status_updates)} status updates")

            # Phase 2: Batch write all at once
            if target_rows or status_updates:
                logger.info("Phase 2: Batch writing to sheets...")
                batch_writer = BatchWriter(self.sheets_client, self.spreadsheet_id)

                batch_result = batch_writer.batch_write_with_updates(
                    source_sheet=self.source_sheet,
                    source_data=[],
                    target_sheet=self.target_sheet,
                    target_data=target_rows,
                    status_updates=status_updates
                )
                logger.info(f"Batch write result: {batch_result}")

                # Validate batch write succeeded
                if batch_result["target_rows_written"] != len(target_rows):
                    raise RuntimeError(
                        f"Incomplete write: expected {len(target_rows)} rows, got {batch_result['target_rows_written']}"
                    )
                if batch_result["status_updates_applied"] != len(status_updates or {}):
                    raise RuntimeError(
                        f"Incomplete status updates: expected {len(status_updates or {})}, got {batch_result['status_updates_applied']}"
                    )

            logger.info(f"Transfer completed: {stats['transferred']} transferred, "
                       f"{stats['already_exists']} duplicates")

            return stats

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            raise

    def _prepare_all_data(self, source_rows: list[list], source_ids_set: set[str] | None = None) -> dict:
        """
        Prepare all data for batch writing.

        Args:
            source_rows: Rows from source sheet
            source_ids_set: Set of normalized IDs to process. If None, process all rows.

        Returns:
            Dictionary with target_rows, status_updates, and statistics
        """
        target_rows = []
        status_updates = {}
        stats = {
            "transferred": 0,
            "already_exists": 0,
            "empty_id": 0,
            "with_status": 0,
            "total_processed": 0,
        }

        for idx, source_row in enumerate(source_rows):
            row_number = idx + 2  # +1 for header, +1 for 1-indexed

            # Get ID_INTERNO
            id_interno = self._get_cell_value(source_row, "ID_INTERNO", self.source_indices)
            id_normalized = self._normalize_text(id_interno)

            # If source_ids_set is provided, only process rows with IDs in the set
            if source_ids_set is not None and id_normalized not in source_ids_set:
                logger.debug(f"Row {row_number}: ID {id_interno} not in source_ids, skipping")
                continue

            stats["total_processed"] += 1

            # Check if has status
            status_idx = self._get_index("STATUS", self.source_indices)
            if status_idx is not None and status_idx < len(source_row):
                status_val = str(source_row[status_idx]).strip()
                if status_val:
                    logger.debug(f"Row {row_number}: Has STATUS, skipping")
                    stats["with_status"] += 1
                    continue

            # Validate ID
            if not id_interno:
                status_updates[row_number] = "Erro: ID_INTERNO vazio"
                stats["empty_id"] += 1
                logger.warning(f"Row {row_number}: Empty ID_INTERNO")
                continue

            # Check duplicates
            if id_normalized in self.existing_ids:
                status_updates[row_number] = "Ja existe"
                stats["already_exists"] += 1
                logger.debug(f"Row {row_number}: Duplicate ID")
                continue

            # Prepare transfer row
            try:
                target_row = self._build_target_row(source_row)
                target_rows.append(target_row)
                self.existing_ids.add(id_normalized)
                status_updates[row_number] = "Transferido"
                stats["transferred"] += 1
                logger.debug(f"Row {row_number}: Prepared for transfer")
            except Exception as e:
                status_updates[row_number] = f"Erro: {str(e)[:40]}"
                logger.error(f"Row {row_number}: {e}")

        return {
            "target_rows": target_rows,
            "status_updates": status_updates,
            "stats": stats
        }

    def _build_target_row(self, source_row: list) -> list:
        """Build a row for target sheet (CONTAORDEM)."""
        # Create empty row
        row = [""] * len(self.target_headers)

        # Map fields
        data_mov = self._get_cell_value(source_row, "DATA MOV.", self.source_indices)
        desc = self._get_cell_value(source_row, "DESCRIÇÃO", self.source_indices)
        desc_norm = self._normalize_text(desc)
        valor = self._get_cell_value(source_row, "IMPORTÂNCIA", self.source_indices)
        valor_abs = abs(self._parse_amount(valor))
        valor_fmt = self._format_number(valor_abs)
        tipo = self._get_cell_value(source_row, "TIPO", self.source_indices)
        id_interno = self._get_cell_value(source_row, "ID_INTERNO", self.source_indices)
        periodo = self._get_month_text(data_mov)

        # Set values
        self._set_cell_value(row, "DATA MOV.", data_mov, self.target_indices)
        self._set_cell_value(row, "DESCRIÇÃO", desc_norm, self.target_indices)
        self._set_cell_value(row, "IMPORTÂNCIA", valor_fmt, self.target_indices)
        self._set_cell_value(row, "TIPO", tipo, self.target_indices)
        self._set_cell_value(row, "PERÍODO", periodo, self.target_indices)
        self._set_cell_value(row, "PROCESSO", "T_EXTRATO", self.target_indices)
        self._set_cell_value(row, "ID_INTERNO", id_interno, self.target_indices)

        return row

    # Helper methods

    def _get_index(self, column_name: str, indices: dict) -> Optional[int]:
        """Get column index."""
        return indices.get(column_name.upper())

    def _get_cell_value(self, row: list, column_name: str, indices: dict) -> str:
        """Get cell value by column name."""
        idx = self._get_index(column_name, indices)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    def _set_cell_value(self, row: list, column_name: str, value: str, indices: dict) -> None:
        """Set cell value by column name."""
        idx = self._get_index(column_name, indices)
        if idx is not None and idx < len(row):
            row[idx] = value

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text."""
        if not text:
            return ""
        text = str(text).replace(" ", "").upper()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Parse amount with comma as decimal."""
        if not value:
            return 0.0
        try:
            return float(str(value).strip().replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _format_number(value: float) -> str:
        """Format number with comma."""
        return f"{value:.2f}".replace(".", ",")

    def _get_month_text(self, data_str: str) -> str:
        """Extract month from date (DD/MM/YYYY)."""
        if not data_str:
            return ""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(str(data_str).strip(), "%d/%m/%Y")
            return self.MESES[date_obj.month - 1]
        except (ValueError, IndexError):
            return ""
