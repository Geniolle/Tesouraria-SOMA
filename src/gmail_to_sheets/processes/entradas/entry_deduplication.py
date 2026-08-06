"""
Entry Deduplication Service

Checks for duplicate entries in CONTAORDEM using data+valor+descrição key.
Prevents transferring same entry twice.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EntryDeduplicationService:
    """Check for duplicate entries before transfer."""

    def __init__(self, sheets_client, spreadsheet_id: str):
        """
        Initialize deduplication service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.target_sheet = "CONTAORDEM"
        self.existing_keys = set()
        self._load_existing_entries()

    def _load_existing_entries(self) -> None:
        """Load existing entries from CONTAORDEM for deduplication."""
        try:
            logger.info(f"Loading existing entries from {self.target_sheet}...")

            headers = self.sheets_client.get_headers(
                self.spreadsheet_id, self.target_sheet
            )

            # Find column indices
            data_idx = None
            valor_idx = None
            desc_idx = None

            for idx, header in enumerate(headers):
                h = str(header).upper().strip()
                if "DATA MOV" in h:
                    data_idx = idx
                elif "IMPORTÂNCIA" in h:
                    valor_idx = idx
                elif "DESCRIÇÃO" in h and "SOMA" not in h:
                    desc_idx = idx

            if data_idx is None or valor_idx is None or desc_idx is None:
                logger.warning(
                    f"Missing columns in {self.target_sheet}: "
                    f"DATA={data_idx}, VALOR={valor_idx}, DESC={desc_idx}"
                )
                return

            # Load all data rows
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.target_sheet}!A2:Z99999",
            ).execute()

            rows = result.get("values", [])

            # Build deduplication keys
            for row in rows:
                if data_idx >= len(row) or valor_idx >= len(row) or desc_idx >= len(row):
                    continue

                data = str(row[data_idx]).strip() if row[data_idx] else ""
                valor = str(row[valor_idx]).strip() if row[valor_idx] else ""
                desc = str(row[desc_idx]).strip() if row[desc_idx] else ""

                if data and valor and desc:
                    key = self._normalize_key(data, valor, desc)
                    self.existing_keys.add(key)

            logger.info(f"Loaded {len(self.existing_keys)} existing entries")

        except Exception as e:
            logger.error(f"Failed to load existing entries: {e}")
            self.existing_keys = set()

    def is_duplicate(self, data: str, valor: str, descricao: str) -> bool:
        """
        Check if entry is duplicate.

        Uses normalized key: data-valor-descrição

        Args:
            data: Date (DD/MM/YYYY)
            valor: Value (with comma decimal)
            descricao: Description

        Returns:
            True if duplicate exists
        """
        key = self._normalize_key(data, valor, descricao)
        is_dup = key in self.existing_keys

        if is_dup:
            logger.debug(f"Duplicate found: {key}")

        return is_dup

    def register_new_entry(self, data: str, valor: str, descricao: str) -> None:
        """
        Register a new entry in deduplication cache.

        Used during batch processing to prevent duplicate detection
        of entries in the same batch.

        Args:
            data: Date
            valor: Value
            descricao: Description
        """
        key = self._normalize_key(data, valor, descricao)
        self.existing_keys.add(key)
        logger.debug(f"Registered entry: {key}")

    @staticmethod
    def _normalize_key(data: str, valor: str, descricao: str) -> str:
        """
        Normalize deduplication key.

        Standardizes:
        - Data format
        - Valor format (normalize decimal)
        - Description (lowercase, strip spaces)

        Args:
            data: Date string
            valor: Value string
            descricao: Description string

        Returns:
            Normalized key
        """
        # Normalize date (just strip)
        data_norm = str(data).strip()

        # Normalize valor (remove spaces, standardize decimal)
        valor_norm = str(valor).strip().replace(" ", "").replace(",", ".")
        try:
            valor_norm = f"{float(valor_norm):.2f}"
        except (ValueError, TypeError):
            valor_norm = valor.strip()

        # Normalize description (lowercase, strip extra spaces)
        desc_norm = str(descricao).strip().lower()
        desc_norm = " ".join(desc_norm.split())  # Remove extra spaces

        return f"{data_norm}|{valor_norm}|{desc_norm}"
