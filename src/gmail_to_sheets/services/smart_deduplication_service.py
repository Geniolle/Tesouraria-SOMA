"""
Smart deduplication by date and value instead of loading all IDs.

Filters by DATA MOV first, then validates VALUE + DESCRIPTION.
Much more efficient than checking against all 3869 existing IDs.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SmartDeduplicationService:
    """Deduplication using date-based filtering and value validation."""

    def __init__(self, sheets_client: Any, spreadsheet_id: str, target_sheet: str = "CONTAORDEM"):
        """Initialize with Sheets client."""
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.target_sheet = target_sheet
        self.cache_by_date: dict[str, dict[tuple[str, str], int]] = {}

    def load_existing_by_date(self, date_str: str) -> dict[tuple[str, str], int]:
        """
        Load existing records from target sheet for a specific date only.

        Args:
            date_str: Format "DD/MM/YYYY" (e.g., "04/08/2026")

        Returns:
            Dictionary: {(valor, descricao_normalized): row_number}
        """
        if date_str in self.cache_by_date:
            return self.cache_by_date[date_str]

        try:
            # Load all data from CONTAORDEM
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=self.sheets_client.get_data_range(self.spreadsheet_id, self.target_sheet),
            ).execute()

            rows = result.get("values", [])
            headers = self.sheets_client.get_headers(self.spreadsheet_id, self.target_sheet)

            # Find column indices
            data_mov_idx = None
            valor_idx = None
            descricao_idx = None

            for i, header in enumerate(headers):
                if "DATA MOV" in str(header).upper():
                    data_mov_idx = i
                elif "IMPORTÂNCIA" in str(header).upper():
                    valor_idx = i
                elif "DESCRIÇÃO" in str(header).upper() and "SOMA" not in str(header).upper():
                    descricao_idx = i

            if data_mov_idx is None or valor_idx is None or descricao_idx is None:
                logger.warning(f"Missing columns: DATA_MOV={data_mov_idx}, VALOR={valor_idx}, DESC={descricao_idx}")
                self.cache_by_date[date_str] = {}
                return {}

            # Filter rows by date
            date_records = {}
            for row_num, row in enumerate(rows, start=2):  # Start from row 2 (after header)
                if data_mov_idx >= len(row):
                    continue

                row_date = str(row[data_mov_idx]).strip()
                if row_date != date_str:
                    continue

                # Extract value and description for this date
                if valor_idx < len(row) and descricao_idx < len(row):
                    valor = self._normalize_amount(str(row[valor_idx]).strip())
                    descricao = self._normalize_text(str(row[descricao_idx]).strip())
                    key = (valor, descricao)
                    date_records[key] = row_num

            self.cache_by_date[date_str] = date_records
            logger.debug(f"Loaded {len(date_records)} records for date {date_str}")
            return date_records

        except Exception as e:
            logger.error(f"Failed to load existing records for date {date_str}: {e}")
            self.cache_by_date[date_str] = {}
            return {}

    def is_duplicate(self, transaction: Any) -> bool:
        """
        Check if record is duplicate using date-based filtering.

        Args:
            transaction: Transaction object with data_mov, valor, descricao attributes

        Returns:
            True if duplicate exists, False otherwise
        """
        # Extract fields from Transaction
        data_mov = str(transaction.data_mov).strip()
        valor = str(transaction.valor).strip()
        descricao = str(transaction.descricao).strip()

        # Load records for this date
        records = self.load_existing_by_date(data_mov)
        if not records:
            return False

        # Normalize for comparison
        valor_norm = self._normalize_amount(valor)
        descricao_norm = self._normalize_text(descricao)
        key = (valor_norm, descricao_norm)

        is_dup = key in records
        if is_dup:
            logger.debug(f"Duplicate found: {data_mov} | {valor_norm} | {descricao_norm}")
        return is_dup

    def register(self, transaction: Any) -> None:
        """
        Register a transaction in the deduplication cache.

        Used during batch writes to prevent duplicate detection of
        transactions written in the same batch, using the same
        normalization as is_duplicate().

        Args:
            transaction: Transaction object with data_mov, valor, descricao attributes
        """
        # Extract fields using exact same normalization as is_duplicate()
        data_mov = str(transaction.data_mov).strip()
        valor = str(transaction.valor).strip()
        descricao = str(transaction.descricao).strip()

        # Normalize for comparison (match is_duplicate logic exactly)
        valor_norm = self._normalize_amount(valor)
        descricao_norm = self._normalize_text(descricao)
        key = (valor_norm, descricao_norm)

        # Load existing records for this date (preserves historical data)
        records = self.load_existing_by_date(data_mov)

        # Add new transaction to cache with a virtual row number
        # Use a negative row number to indicate it's from current batch
        records[key] = -1

        logger.debug(f"Registered in cache: {data_mov} | {valor_norm} | {descricao_norm}")

    def _normalize_amount(self, amount_str: str) -> str:
        """Normalize amount for comparison (remove spaces, standardize decimal)."""
        # Remove spaces
        amount_str = amount_str.replace(" ", "")
        # Convert comma to dot for comparison
        amount_str = amount_str.replace(",", ".")
        try:
            # Parse as float and format to 2 decimals
            return f"{float(amount_str):.2f}"
        except ValueError:
            return amount_str

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (lowercase, strip accents)."""
        text = text.lower().strip()
        # Remove accents (basic version)
        accents = {
            'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n'
        }
        for accent, replacement in accents.items():
            text = text.replace(accent, replacement)
        return text

    def clear_cache(self):
        """Clear date-based cache."""
        self.cache_by_date = {}
        logger.debug("Deduplication cache cleared")
