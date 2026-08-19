"""Sheets writer service for the extrato process."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.models.transaction import Transaction
from src.gmail_to_sheets.processes.extrato.sheets_writer_support import (
    format_decimal,
    load_existing_dedup_keys,
    load_headers,
    load_last_sequence,
    map_columns,
    parse_opening_balance,
    transaction_to_row,
    write_closing_balance,
)
from src.gmail_to_sheets.validators.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class SheetsWriter:
    """Service to write transactions to Google Sheets."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        sheet_name: str,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.headers = self._load_headers()
        self.column_indices = self._map_columns()
        self.last_sequence = self._load_last_sequence()

    def _load_headers(self) -> list[str]:
        """Load headers from sheet."""
        try:
            headers = load_headers(self.sheets_client, self.spreadsheet_id, self.sheet_name)
            logger.info("Loaded %s columns from %s", len(headers), self.sheet_name)
            return headers
        except Exception as exc:
            logger.error("Failed to load headers: %s", exc)
            raise

    def _map_columns(self) -> dict[str, int]:
        """Map column names to indices."""
        return map_columns(self.headers)

    def _load_last_sequence(self) -> int:
        """Load the last ID_INTERNO sequence number from sheet."""
        try:
            return load_last_sequence(
                self.sheets_client,
                self.spreadsheet_id,
                self.sheet_name,
                self.column_indices,
            )
        except Exception as exc:
            logger.warning("Error loading last sequence: %s, starting from 0", exc)
            return 0

    def load_existing_dedup_keys(self, dedup_service: DeduplicationService) -> None:
        """Load existing transactions for deduplication."""
        try:
            logger.info("Loading existing transactions for deduplication...")
            load_existing_dedup_keys(
                self.sheets_client,
                self.spreadsheet_id,
                self.sheet_name,
                self.column_indices,
                dedup_service,
            )
        except Exception as exc:
            logger.error("Failed to load existing transactions: %s", exc)
            raise

    def write_transactions(
        self,
        transactions: list[Transaction],
        opening_balance: Optional[str] = None,
        dedup_service: Optional[DeduplicationService] = None,
    ) -> dict:
        """Write transactions to sheet with progressive balance calculation."""
        try:
            logger.info("Writing %s transactions...", len(transactions))

            rows_to_write = []
            written_ids = []
            written = 0
            skipped = 0
            next_sequence = self.last_sequence + 1
            current_balance = parse_opening_balance(opening_balance)

            logger.info("Starting balance: %s", current_balance)
            logger.info("Starting ID sequence from: %s", next_sequence)

            for txn in transactions:
                try:
                    valor_decimal = Decimal(str(txn.valor).replace(",", "."))
                except (ValueError, TypeError):
                    raise ValueError(f"Invalid transaction value: {txn.valor}")

                current_balance += valor_decimal

                if dedup_service and dedup_service.is_duplicate(txn):
                    logger.debug("Skipping duplicate: %s", txn.dedup_key())
                    skipped += 1
                    continue

                sequencial = next_sequence
                next_sequence += 1
                id_interno = f"EXT{str(sequencial).zfill(10)}"

                row = transaction_to_row(
                    txn=txn,
                    headers=self.headers,
                    column_indices=self.column_indices,
                    saldo_contabilistico=current_balance,
                    sequencial=sequencial,
                )
                rows_to_write.append(row)
                written_ids.append(id_interno)
                written += 1

                if dedup_service:
                    dedup_service.register(txn)

            if not rows_to_write:
                logger.warning("No new transactions to write")
                return {
                    "written": 0,
                    "skipped": skipped,
                    "total": len(transactions),
                    "written_ids": [],
                }

            result = self.sheets_client.append_rows(
                self.spreadsheet_id,
                self.sheet_name,
                rows_to_write,
            )

            logger.info("Successfully wrote %s transactions with IDs: %s", written, written_ids)
            return {
                "written": written,
                "skipped": skipped,
                "total": len(transactions),
                "written_ids": written_ids,
                "api_response": result,
            }
        except Exception as exc:
            logger.error("Failed to write transactions: %s", exc)
            raise

    def _transaction_to_row(
        self,
        txn: Transaction,
        saldo_contabilistico=None,
        sequencial: int = 0,
    ) -> list:
        """Convert transaction to sheet row with formatting."""
        return transaction_to_row(
            txn=txn,
            headers=self.headers,
            column_indices=self.column_indices,
            saldo_contabilistico=saldo_contabilistico,
            sequencial=sequencial,
        )

    def write_closing_balance(self, row_number: int, balance: str) -> None:
        """Write closing balance to specific row."""
        try:
            write_closing_balance(
                self.sheets_client,
                self.spreadsheet_id,
                self.sheet_name,
                self.column_indices,
                row_number,
                balance,
            )
        except Exception as exc:
            logger.error("Failed to write closing balance: %s", exc)
            raise
