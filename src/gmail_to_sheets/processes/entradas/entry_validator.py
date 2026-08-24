"""
Entry Validator Service

Validates entries from DÍZIMOS/OFERTAS sheet before transfer to CONTAORDEM.
Checks all business rules and criteria.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EntryValidatorError(Exception):
    """Raised when entry validation fails."""
    pass


class EntryValidator:
    """Validate entries from DÍZIMOS/OFERTAS sheet."""

    def __init__(self, sheets_client, spreadsheet_id: str):
        """
        Initialize validator.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = "DÍZIMOS/OFERTAS"
        self.column_indices = self._load_column_indices()

    def _load_column_indices(self) -> dict:
        """Load and map column indices from header row."""
        try:
            headers = self.sheets_client.get_headers(
                self.spreadsheet_id, self.source_sheet
            )

            indices = {}
            for idx, header in enumerate(headers):
                header_name = str(header).upper().strip() if header else ""
                indices[header_name] = idx

            logger.info(f"Loaded {len(indices)} columns from {self.source_sheet}")
            return indices

        except Exception as e:
            logger.error(f"Failed to load column indices: {e}")
            raise EntryValidatorError(f"Failed to load columns: {e}") from e

    def is_valid_entry(self, row: list, row_number: int) -> tuple[bool, Optional[str]]:
        """
        Validate if entry meets transfer criteria.

        Criteria:
        - TIPO must be "DÍZIMOS/OFERTAS" or "DIA VERBO MISSÔES"
        - DOC.SOMA must be filled (não vazio)
        - FINANCE must be empty
        - VALOR must be > 0
        - DATA must exist and be valid

        Args:
            row: Row data from sheet
            row_number: Row number for logging

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Extract field values
            data = self._get_field(row, "DATA")
            tipo = self._get_field(row, "TIPO")
            doc_soma = self._get_field(row, "DOC. SOMA")
            finance = self._get_field(row, "FINANCE")
            valor = self._get_field(row, "VALOR")

            # Validate DATA
            if not data:
                return False, "DATA vazia"

            # Validate TIPO
            if tipo not in ["DÍZIMOS/OFERTAS", "DIA VERBO MISSÔES"]:
                return False, f"TIPO inválido: {tipo}"

            # Validate DOC.SOMA (must be filled/não vazio)
            if not doc_soma or not str(doc_soma).strip():
                return False, "DOC.SOMA está vazio"

            # Validate FINANCE (must be empty)
            if finance and str(finance).strip():
                return False, "FINANCE não está vazio"

            # Validate VALOR
            if not valor:
                return False, "VALOR vazio"

            try:
                valor_decimal = float(str(valor).replace(",", "."))
                if valor_decimal <= 0:
                    return False, f"VALOR <= 0: {valor}"
            except (ValueError, TypeError):
                return False, f"VALOR inválido: {valor}"

            return True, None

        except Exception as e:
            logger.error(f"Validation error on row {row_number}: {e}")
            return False, f"Erro na validação: {str(e)[:50]}"

    def get_validation_errors(self, row: list, row_number: int) -> list[str]:
        """
        Get all validation errors for a row.

        Args:
            row: Row data
            row_number: Row number

        Returns:
            List of error messages
        """
        errors = []

        try:
            data = self._get_field(row, "DATA")
            tipo = self._get_field(row, "TIPO")
            doc_soma = self._get_field(row, "DOC. SOMA")
            finance = self._get_field(row, "FINANCE")
            valor = self._get_field(row, "VALOR")

            if not data:
                errors.append("DATA vazia")

            if tipo not in ["DÍZIMOS/OFERTAS", "DIA VERBO MISSÔES"]:
                errors.append(f"TIPO inválido: {tipo}")

            if not doc_soma or not str(doc_soma).strip():
                errors.append("DOC.SOMA está vazio")

            if finance and str(finance).strip():
                errors.append("FINANCE não está vazio")

            if not valor:
                errors.append("VALOR vazio")
            else:
                try:
                    valor_decimal = float(str(valor).replace(",", "."))
                    if valor_decimal <= 0:
                        errors.append(f"VALOR <= 0: {valor}")
                except (ValueError, TypeError):
                    errors.append(f"VALOR inválido: {valor}")

        except Exception as e:
            errors.append(f"Erro na validação: {str(e)[:50]}")

        return errors

    def _get_field(self, row: list, field_name: str) -> Optional[str]:
        """
        Get field value from row by name.

        Args:
            row: Row data
            field_name: Column name (case-insensitive)

        Returns:
            Field value or None
        """
        key = field_name.upper().strip()
        idx = self.column_indices.get(key)

        if idx is None or idx >= len(row):
            return None

        value = row[idx]
        return str(value).strip() if value else None
