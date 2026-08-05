"""
Transaction Recovery Service

Recovers transactions from T_EXTRATO when they already exist (partial execution recovery).
Matches new transactions against existing rows using:
1. Data MOV (date)
2. IMPORTÂNCIA (value, normalized)
3. DESCRIÇÃO (description, normalized)
4. Saldo Contabilístico (progressive balance) for disambiguation

This enables idempotent re-execution: if a run partially completes (write succeeds,
transfer fails), re-running will:
- Detect already-written transactions
- Recover their IDs (EXT0000003366, etc.)
- Continue with transfer, balance, archive
- Never duplicate rows
"""

import logging
import unicodedata
from decimal import Decimal
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.models.transaction import Transaction

logger = logging.getLogger(__name__)


class TransactionRecoveryService:
    """Recover transaction IDs from existing T_EXTRATO rows."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        source_sheet: str = "T_EXTRATO",
    ):
        """
        Initialize recovery service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
            source_sheet: Sheet to recover from (default: T_EXTRATO)
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self._load_sheet_data()

    def _load_sheet_data(self) -> None:
        """Load all data from source sheet for analysis."""
        try:
            logger.debug(f"Loading data from {self.source_sheet}...")
            range_name = f"{self.source_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            self.rows = result.get("values", [])
            self.headers = self.sheets_client.get_headers(
                self.spreadsheet_id, self.source_sheet
            )

            # Build column indices
            self._build_indices()

            logger.info(
                f"Loaded {len(self.rows)} rows from {self.source_sheet}"
            )
        except Exception as e:
            logger.error(f"Failed to load sheet data: {e}")
            self.rows = []
            self.headers = []
            self._build_indices()

    def _build_indices(self) -> None:
        """Build column indices from headers."""
        self.data_mov_idx = None
        self.valor_idx = None
        self.desc_idx = None
        self.id_idx = None
        self.saldo_idx = None

        for i, header in enumerate(self.headers):
            h = str(header).upper().strip()
            if "DATA MOV" in h:
                self.data_mov_idx = i
            elif "IMPORTÂNCIA" in h:
                self.valor_idx = i
            elif "DESCRIÇÃO" in h and "SOMA" not in h:
                self.desc_idx = i
            elif "ID_INTERNO" in h:
                self.id_idx = i
            elif "SALDO CONTABILÍSTICO" in h:
                self.saldo_idx = i

    def recover_id(
        self,
        transaction: Transaction,
        opening_balance: Decimal,
        position_in_batch: int,
    ) -> Optional[str]:
        """
        Recover ID for a transaction that may already exist in T_EXTRATO.

        Uses data + value + description to find candidates, then disambiguates
        using progressive balance from opening_balance + sum of prior transactions.

        Args:
            transaction: Transaction to recover
            opening_balance: Opening balance for this MT940 file
            position_in_batch: Position of this transaction in the batch (0-indexed)

        Returns:
            ID_INTERNO if found (e.g., "EXT0000003366"), or None if not found/ambiguous
        """
        if not self._can_search():
            return None

        try:
            # Normalize search values
            data_str = str(transaction.data_mov).strip()
            valor_norm = self._normalize_amount(str(transaction.valor))
            desc_norm = self._normalize_text(str(transaction.descricao))

            # Calculate expected balance at this transaction
            expected_balance = opening_balance + transaction.valor

            # Find all candidate rows
            candidates = []

            for row_idx, row in enumerate(self.rows):
                # Skip rows before our search keys
                if (
                    self.data_mov_idx is None
                    or self.valor_idx is None
                    or self.desc_idx is None
                ):
                    continue

                # Get row values
                row_data = self._get_safe(row, self.data_mov_idx, "")
                row_valor = self._get_safe(row, self.valor_idx, "")
                row_desc = self._get_safe(row, self.desc_idx, "")
                row_id = self._get_safe(row, self.id_idx, "")
                row_saldo = self._get_safe(row, self.saldo_idx, "")

                # Check if matches our transaction
                if (
                    data_str == str(row_data).strip()
                    and valor_norm == self._normalize_amount(str(row_valor))
                    and desc_norm == self._normalize_text(str(row_desc))
                ):
                    candidates.append(
                        {
                            "row_idx": row_idx,
                            "id": row_id,
                            "saldo": row_saldo,
                            "row_num": row_idx + 2,  # +1 header, +1 for 1-indexed
                        }
                    )

            if not candidates:
                return None  # Not found

            if len(candidates) == 1:
                # Unique match
                logger.info(
                    f"Recovered ID {candidates[0]['id']} for {data_str} | {valor_norm} | {desc_norm}"
                )
                return candidates[0]["id"]

            # Multiple candidates - disambiguate using balance
            if self.saldo_idx is not None:
                saldo_norm = self._normalize_amount(str(expected_balance))

                for cand in candidates:
                    cand_saldo_norm = self._normalize_amount(str(cand["saldo"]))
                    if saldo_norm == cand_saldo_norm:
                        logger.info(
                            f"Recovered ID {cand['id']} (disambiguated by balance {saldo_norm})"
                        )
                        return cand["id"]

            # Could not disambiguate - return None (will be treated as new)
            logger.warning(
                f"Found {len(candidates)} candidates for {data_str} | {valor_norm} | {desc_norm}, "
                f"could not disambiguate by balance, treating as new"
            )
            return None

        except Exception as e:
            logger.debug(f"Recovery lookup failed: {e}")
            return None

    def _can_search(self) -> bool:
        """Check if search indices are available."""
        return (
            self.data_mov_idx is not None
            and self.valor_idx is not None
            and self.desc_idx is not None
            and self.id_idx is not None
        )

    @staticmethod
    def _get_safe(row: list, idx: Optional[int], default: str = "") -> str:
        """Safely get row value by index."""
        if idx is None or idx >= len(row):
            return default
        return str(row[idx]).strip() if row[idx] else default

    @staticmethod
    def _normalize_amount(amount_str: str) -> str:
        """Normalize amount for comparison."""
        if not amount_str:
            return ""
        amount_str = amount_str.replace(" ", "").replace(",", ".")
        try:
            return f"{float(amount_str):.2f}"
        except (ValueError, TypeError):
            return amount_str

    def recover_batch(
        self,
        mt940_file,
    ) -> list[str]:
        """
        Recover IDs for all transactions in an MT940 file.

        Uses progressive balance calculation to resolve ambiguities.

        Args:
            mt940_file: MT940File object with transactions

        Returns:
            List of recovered ID_INTERNO values (e.g., ["EXT0000003366", "EXT0000003367"])
        """
        try:
            recovered = []
            running_balance = Decimal(str(mt940_file.header.saldo_abertura))

            for idx, txn in enumerate(mt940_file.transactions):
                recovered_id = self.recover_id(
                    transaction=txn,
                    opening_balance=running_balance,
                    position_in_batch=idx,
                )

                if recovered_id:
                    recovered.append(recovered_id)

                # Update running balance for next iteration
                running_balance += Decimal(str(txn.valor))

            if recovered:
                logger.info(f"Recovered {len(recovered)} total IDs from {len(mt940_file.transactions)} transactions")

            return recovered

        except Exception as e:
            logger.debug(f"Recovery batch failed: {e}, continuing without recovery")
            return []

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison (case-insensitive, accent-insensitive)."""
        if not text:
            return ""
        text = text.lower().strip()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
