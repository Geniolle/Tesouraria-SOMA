"""
Transfer Service

Handles transferring transactions from T_EXTRATO to CONTAORDEM sheet.
Uses batch operations for optimized performance.
"""

import logging
import unicodedata
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.services.batch_writer import BatchWriter
from src.gmail_to_sheets.models.transaction import Transaction


logger = logging.getLogger(__name__)


class TransferService:
    """Service to transfer transactions from T_EXTRATO to CONTAORDEM."""

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
        """
        Initialize transfer service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
            source_sheet: Source sheet name (default: T_EXTRATO)
            target_sheet: Target sheet name (default: CONTAORDEM)
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.target_sheet = target_sheet

        # Load headers and indices
        self.source_headers = self._load_headers(source_sheet)
        self.target_headers = self._load_headers(target_sheet)

        self.source_indices = self._map_columns(self.source_headers)
        self.target_indices = self._map_columns(self.target_headers)

        # Validate required columns
        self._validate_columns()

        # Load existing IDs from target sheet
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
            indices[header.strip()] = idx
        return indices

    def _validate_columns(self) -> None:
        """Validate required columns exist in both sheets."""
        required_source = ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "STATUS", "ID_INTERNO"]
        required_target = ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "PERÍODO", "PROCESSO", "ID_INTERNO"]

        missing_source = [col for col in required_source if col not in self.source_indices]
        missing_target = [col for col in required_target if col not in self.target_indices]

        if missing_source:
            raise RuntimeError(f"Missing columns in {self.source_sheet}: {missing_source}")
        if missing_target:
            raise RuntimeError(f"Missing columns in {self.target_sheet}: {missing_target}")

        logger.info("✅ All required columns found in both sheets")

    def _load_existing_ids(self) -> set:
        """Load all existing ID_INTERNO from target sheet."""
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
                    id_val = self._normalize_text(row[id_idx])
                    existing_ids.add(id_val)

            logger.info(f"Loaded {len(existing_ids)} existing IDs from {self.target_sheet}")
            return existing_ids

        except Exception as e:
            logger.error(f"Failed to load existing IDs: {e}")
            raise

    def transfer_pending(self) -> dict:
        """
        Transfer all pending transactions from source to target sheet.

        Returns:
            Transfer statistics
        """
        try:
            logger.info(f"Starting transfer from {self.source_sheet} to {self.target_sheet}")

            # Load source data
            range_name = f"{self.source_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            source_rows = result.get("values", [])
            logger.info(f"Found {len(source_rows)} rows in {self.source_sheet}")

            stats = {
                "transferred": 0,
                "already_exists": 0,
                "empty_id": 0,
                "with_status": 0,
                "total_processed": 0,
            }

            # Batch updates for status column
            status_updates = {}

            # Process each row
            for idx, row in enumerate(source_rows):
                row_number = idx + 2  # +1 for header, +1 for 1-indexed

                # Check status
                status_idx = self.source_indices.get("STATUS")
                if status_idx is not None and status_idx < len(row):
                    status_val = row[status_idx].strip()
                    if status_val:
                        logger.debug(f"Row {row_number}: STATUS='{status_val}', skipping")
                        stats["with_status"] += 1
                        stats["total_processed"] += 1
                        continue

                # Get ID_INTERNO
                id_idx = self.source_indices.get("ID_INTERNO")
                if id_idx is None or id_idx >= len(row):
                    status_updates[row_number] = "Erro: ID_INTERNO vazio"
                    stats["empty_id"] += 1
                    stats["total_processed"] += 1
                    continue

                id_interno = row[id_idx].strip()
                id_normalized = self._normalize_text(id_interno)

                # Check if empty
                if not id_interno:
                    status_updates[row_number] = "Erro: ID_INTERNO vazio"
                    logger.warning(f"Row {row_number}: ID_INTERNO is empty")
                    stats["empty_id"] += 1
                    stats["total_processed"] += 1
                    continue

                # Check if already exists
                if id_normalized in self.existing_ids:
                    status_updates[row_number] = "Ja existe"
                    logger.info(f"Row {row_number}: ID '{id_interno}' already in {self.target_sheet}")
                    stats["already_exists"] += 1
                    stats["total_processed"] += 1
                    continue

                # Transfer row
                try:
                    self._transfer_row(row_number, row, id_interno)
                    self.existing_ids.add(id_normalized)
                    status_updates[row_number] = "Transferido"
                    logger.info(f"Row {row_number}: ID '{id_interno}' transferred [OK]")
                    stats["transferred"] += 1
                except Exception as e:
                    status_updates[row_number] = f"Erro: {str(e)[:50]}"
                    logger.error(f"Row {row_number}: Transfer failed: {e}")

                stats["total_processed"] += 1

            # Apply status updates in batch (to avoid quota exceeded)
            logger.info(f"Updating status for {len(status_updates)} rows...")
            self._update_status_batch(status_updates)

            logger.info(f"Transfer completed: {stats['transferred']} transferred, "
                       f"{stats['already_exists']} duplicates, "
                       f"{stats['empty_id']} empty IDs, "
                       f"{stats['with_status']} with status")

            return stats

        except Exception as e:
            logger.error(f"Transfer process failed: {e}")
            raise

    def _transfer_row(self, row_number: int, source_row: list, id_interno: str) -> None:
        """
        Transfer a single row to target sheet.

        Args:
            row_number: Row number in source sheet (1-indexed)
            source_row: Row data from source sheet
            id_interno: ID_INTERNO value
        """
        # Extract source values
        data_mov_idx = self.source_indices.get("DATA MOV.")
        desc_idx = self.source_indices.get("DESCRIÇÃO")
        import_idx = self.source_indices.get("IMPORTÂNCIA")
        tipo_idx = self.source_indices.get("TIPO")

        data_mov = source_row[data_mov_idx] if data_mov_idx < len(source_row) else ""
        descricao = source_row[desc_idx] if desc_idx < len(source_row) else ""
        importancia_val = source_row[import_idx] if import_idx < len(source_row) else "0"
        tipo = source_row[tipo_idx] if tipo_idx < len(source_row) else ""

        # Process values
        descricao_norm = self._normalize_text(descricao)
        importancia_num = self._parse_amount(importancia_val)
        importancia_abs = abs(importancia_num)
        importancia_fmt = self._format_number(importancia_abs)
        periodo = self._get_month_text(data_mov)

        # Get target row number
        target_row = self._get_next_row()

        # Write to target sheet
        target_date_col = self.target_indices.get("DATA MOV.") + 1
        target_desc_col = self.target_indices.get("DESCRIÇÃO") + 1
        target_import_col = self.target_indices.get("IMPORTÂNCIA") + 1
        target_tipo_col = self.target_indices.get("TIPO") + 1
        target_periodo_col = self.target_indices.get("PERÍODO") + 1
        target_processo_col = self.target_indices.get("PROCESSO") + 1
        target_id_col = self.target_indices.get("ID_INTERNO") + 1

        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_date_col, data_mov
        )
        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_desc_col, descricao_norm
        )
        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_import_col, importancia_fmt
        )
        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_tipo_col, tipo
        )
        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_periodo_col, periodo
        )
        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_processo_col, "T_EXTRATO"
        )
        self.sheets_client.update_cell(
            self.spreadsheet_id, self.target_sheet, target_row, target_id_col, id_interno
        )

    def _get_next_row(self) -> int:
        """Get the next available row in target sheet."""
        try:
            last_row = self.sheets_client.get_last_row(self.spreadsheet_id, self.target_sheet)
            return last_row + 1
        except Exception as e:
            logger.error(f"Failed to get last row: {e}")
            raise

    def _update_status_batch(self, status_updates: dict) -> None:
        """Batch update STATUS fields in source sheet."""
        if not status_updates:
            return

        try:
            status_col = self.source_indices.get("STATUS")
            if status_col is None:
                return

            # Build batch update request
            requests = []
            for row_number, status_value in status_updates.items():
                col_letter = self._number_to_column(status_col + 1)
                range_name = f"{self.source_sheet}!{col_letter}{row_number}"

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

    @staticmethod
    def _number_to_column(col_num: int) -> str:
        """Convert column number to letter (1=A, 2=B, etc)."""
        col_letter = ""
        while col_num > 0:
            col_num -= 1
            col_letter = chr(65 + col_num % 26) + col_letter
            col_num //= 26
        return col_letter

    def _set_status(self, row_number: int, status: str) -> None:
        """Set STATUS field in source sheet."""
        try:
            status_col = self.source_indices.get("STATUS") + 1
            self.sheets_client.update_cell(
                self.spreadsheet_id, self.source_sheet, row_number, status_col, status
            )
        except Exception as e:
            logger.warning(f"Failed to set status for row {row_number}: {e}")

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text: remove accents and spaces."""
        if not text:
            return ""

        # Remove spaces
        text = str(text).replace(" ", "")

        # Remove accents
        normalized = unicodedata.normalize("NFD", text)
        without_accents = "".join(
            char for char in normalized if unicodedata.category(char) != "Mn"
        )

        return without_accents.upper()

    @staticmethod
    def _parse_amount(amount_str: str) -> float:
        """Parse amount string (handles comma as decimal separator)."""
        if not amount_str:
            return 0.0

        try:
            amount_str = str(amount_str).strip()
            amount_str = amount_str.replace(",", ".")
            return float(amount_str)
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _format_number(value: float) -> str:
        """Format number with comma as decimal separator."""
        return f"{value:.2f}".replace(".", ",")

    def _get_month_text(self, data_str: str) -> str:
        """Extract month name from date string (DD/MM/YYYY)."""
        if not data_str:
            return ""

        try:
            # Try to parse DD/MM/YYYY format
            date_obj = datetime.strptime(data_str, "%d/%m/%Y")
            return self.MESES[date_obj.month - 1]
        except (ValueError, IndexError):
            logger.debug(f"Could not parse date: {data_str}")
            return ""
