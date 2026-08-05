"""
Sheets Writer Service

Handles writing parsed transactions to Google Sheets.
"""

import logging
from datetime import datetime
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.models.transaction import Transaction
from src.gmail_to_sheets.validators.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class SheetsWriter:
    """Service to write transactions to Google Sheets."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        sheet_name: str,
    ):
        """
        Initialize Sheets writer.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
            sheet_name: Target sheet name
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.headers = self._load_headers()
        self.column_indices = self._map_columns()
        self.last_sequence = self._load_last_sequence()

    def _load_headers(self) -> list[str]:
        """
        Load headers from sheet.

        Returns:
            List of header names
        """
        try:
            headers = self.sheets_client.get_headers(
                self.spreadsheet_id, self.sheet_name
            )
            logger.info(f"Loaded {len(headers)} columns from {self.sheet_name}")
            return headers
        except Exception as e:
            logger.error(f"Failed to load headers: {e}")
            raise

    def _map_columns(self) -> dict[str, int]:
        """
        Map column names to indices.

        Returns:
            Dictionary mapping column name to 0-indexed position
        """
        indices = {}
        for idx, header in enumerate(self.headers):
            indices[header.strip()] = idx
        return indices

    def _load_last_sequence(self) -> int:
        """
        Load the last ID_INTERNO sequence number from sheet.

        Returns:
            Last sequence number (or 0 if no IDs found)
        """
        try:
            id_idx = self.column_indices.get("ID_INTERNO")
            if id_idx is None:
                logger.debug("ID_INTERNO column not found, starting from 0")
                return 0

            # Get all data rows - use large range to capture all
            range_name = f"{self.sheet_name}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            if not rows:
                logger.debug("No existing transactions, starting from 0")
                return 0

            # Find highest sequence number by scanning all rows
            max_sequence = 0
            for row in rows:
                if id_idx < len(row) and row[id_idx]:
                    id_interno = row[id_idx].strip()
                    if id_interno and id_interno.startswith("EXT"):
                        try:
                            # Extract numeric part from both formats:
                            # EXT0000003365 -> 3365
                            # EXT0001000016 -> 1000016
                            numeric_part = int(id_interno[3:])
                            max_sequence = max(max_sequence, numeric_part)
                        except (ValueError, IndexError):
                            logger.debug(f"Could not parse ID: {id_interno}")
                            pass

            logger.info(f"Found last ID_INTERNO sequence: {max_sequence} (found {len(rows)} rows)")
            return max_sequence

        except Exception as e:
            logger.warning(f"Error loading last sequence: {e}, starting from 0")
            return 0

    def load_existing_dedup_keys(
        self, dedup_service: DeduplicationService
    ) -> None:
        """
        Load existing transactions for deduplication.

        Args:
            dedup_service: Deduplication service to populate
        """
        try:
            logger.info("Loading existing transactions for deduplication...")

            # Get all data rows (skip header) - use large range to capture all
            range_name = f"{self.sheet_name}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])

            if not rows:
                logger.info("No existing transactions found")
                return

            # Get column indices safely
            data_mov_idx = self.column_indices.get("DATA MOV.")
            desc_idx = self.column_indices.get("DESCRIÇÃO")
            valor_idx = self.column_indices.get("IMPORTÂNCIA")

            if data_mov_idx is None or desc_idx is None or valor_idx is None:
                logger.error("Missing required columns for deduplication")
                return

            existing_keys = set()
            for row in rows:
                try:
                    # Build key from: DATA MOV | DESCRICAO | IMPORTANCIA
                    if data_mov_idx < len(row) and desc_idx < len(row) and valor_idx < len(row):
                        data_mov = str(row[data_mov_idx]).strip() if row[data_mov_idx] else ""
                        descricao = str(row[desc_idx]).strip() if row[desc_idx] else ""
                        valor = str(row[valor_idx]).strip() if row[valor_idx] else ""

                        if data_mov and descricao and valor:
                            key = f"{data_mov}|{descricao}|{valor}"
                            existing_keys.add(key)
                except Exception as e:
                    logger.debug(f"Error processing row: {e}")
                    continue

            dedup_service.add_existing(existing_keys)
            logger.info(f"Loaded {len(existing_keys)} existing transactions from {len(rows)} rows")

        except Exception as e:
            logger.error(f"Failed to load existing transactions: {e}")
            raise

    def write_transactions(
        self,
        transactions: list[Transaction],
        opening_balance: Optional[str] = None,
        dedup_service: Optional[DeduplicationService] = None,
    ) -> dict:
        """
        Write transactions to sheet with progressive balance calculation.

        Args:
            transactions: List of transactions to write
            opening_balance: Opening balance from MT940 (used as first saldo)
            dedup_service: Optional deduplication service

        Returns:
            Write statistics
        """
        try:
            logger.info(f"Writing {len(transactions)} transactions...")

            rows_to_write = []
            written = 0
            skipped = 0
            next_sequence = self.last_sequence + 1

            # Initialize balance from opening_balance (convert from string if needed)
            if opening_balance:
                try:
                    if isinstance(opening_balance, str):
                        current_balance = float(opening_balance.replace(",", "."))
                    else:
                        current_balance = float(opening_balance)
                except (ValueError, AttributeError):
                    current_balance = 0.0
            else:
                current_balance = 0.0

            logger.info(f"Starting ID sequence from: {next_sequence}")

            for txn in transactions:
                # Check for duplicates
                if dedup_service and dedup_service.is_duplicate(txn):
                    logger.debug(f"Skipping duplicate: {txn.dedup_key()}")
                    skipped += 1
                    continue

                # Calculate progressive balance
                valor_num = float(txn.valor)
                current_balance += valor_num

                # Generate sequential ID using last known sequence
                sequencial = next_sequence
                next_sequence += 1

                # Build row with calculated balance and ID
                row = self._transaction_to_row(
                    txn,
                    saldo_contabilistico=current_balance,
                    sequencial=sequencial,
                )
                rows_to_write.append(row)
                written += 1

                if dedup_service:
                    dedup_service.register(txn)

            if not rows_to_write:
                logger.warning("No new transactions to write")
                return {
                    "written": 0,
                    "skipped": skipped,
                    "total": len(transactions),
                }

            # Append to sheet
            result = self.sheets_client.append_rows(
                self.spreadsheet_id,
                self.sheet_name,
                rows_to_write,
            )

            logger.info(f"Successfully wrote {written} transactions")

            return {
                "written": written,
                "skipped": skipped,
                "total": len(transactions),
                "api_response": result,
            }

        except Exception as e:
            logger.error(f"Failed to write transactions: {e}")
            raise

    def _transaction_to_row(
        self, txn: Transaction, saldo_contabilistico: Optional[float] = None, sequencial: int = 0
    ) -> list:
        """
        Convert transaction to sheet row with formatting.

        Args:
            txn: Transaction to convert
            saldo_contabilistico: Calculated progressive balance
            sequencial: Sequential number for ID_INTERNO generation

        Returns:
            List of values in column order
        """
        # Create row with empty values for all columns
        row = [""] * len(self.headers)

        # Format IMPORTÂNCIA with 0,00 format
        valor_formatado = f"{float(txn.valor):.2f}".replace(".", ",")

        # Format SALDO CONTABILÍSTICO if provided
        saldo_formatado = ""
        if saldo_contabilistico is not None:
            saldo_formatado = f"{saldo_contabilistico:.2f}".replace(".", ",")

        # Generate ID_INTERNO if not set
        # Format: EXT0000NNNNN (e.g., EXT0000003366)
        id_interno = txn.id_interno
        if not id_interno and sequencial > 0:
            id_interno = f"EXT{str(sequencial).zfill(10)}"

        # Map transaction fields to columns
        column_mapping = {
            "DATA MOV.": txn.data_mov,
            "DATA VALOR": txn.data_valor,
            "DESCRIÇÃO": txn.descricao,
            "IMPORTÂNCIA": valor_formatado,
            "TIPO": txn.tipo,
            "TIMESTAMP": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "SALDO CONTABILÍSTICO": saldo_formatado,
            "ID_INTERNO": id_interno,
        }

        # Fill in values
        for col_name, value in column_mapping.items():
            idx = self.column_indices.get(col_name)
            if idx is not None:
                row[idx] = value

        return row

    def write_closing_balance(self, row_number: int, balance: str) -> None:
        """
        Write closing balance to specific row.

        Args:
            row_number: Row number (1-indexed)
            balance: Balance value
        """
        try:
            saldo_idx = self.column_indices.get("SALDO CONTABILÍSTICO", 6)
            if saldo_idx is not None:
                self.sheets_client.update_cell(
                    self.spreadsheet_id,
                    self.sheet_name,
                    row_number,
                    saldo_idx + 1,  # Convert to 1-indexed
                    balance,
                )
        except Exception as e:
            logger.error(f"Failed to write closing balance: {e}")
            raise
