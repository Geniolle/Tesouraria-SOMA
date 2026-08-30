"""Validation rules for SAÍDAS rows before transfer to CONTAORDEM."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SaidaValidatorError(Exception):
    """Raised when SAÍDAS validation cannot be initialized."""


class SaidaValidator:
    """Validate a SAÍDAS row for transfer to CONTAORDEM."""

    source_sheet = "SAÍDAS"

    def __init__(
        self,
        sheets_client,
        spreadsheet_id: str,
        headers: list[str] | None = None,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.column_indices = self._load_column_indices(headers)

    def _load_column_indices(self, headers: list[str] | None) -> dict[str, int]:
        try:
            if headers is None:
                headers = self.sheets_client.get_headers(
                    self.spreadsheet_id,
                    self.source_sheet,
                )

            return {
                str(header).upper().strip(): index
                for index, header in enumerate(headers)
                if header
            }
        except Exception as error:
            raise SaidaValidatorError(
                f"Failed to load SAÍDAS headers: {error}"
            ) from error

    def is_valid_entry(
        self,
        row: list,
        row_number: int,
    ) -> tuple[bool, Optional[str]]:
        """Return whether a row is ready for the finance transfer process.

        Business criteria:
        - ID_INTERNO must be SAI + 10 digits
        - DATA must be filled
        - TIPO must be PAGAMENTO
        - STATUS DA TESOURARIA must be Concluído
        - DOC. SOMA must be filled
        - FINANCE must be empty
        - VALOR DA COMPRA must be greater than zero
        """
        try:
            id_interno = self.get_field(row, "ID_INTERNO")
            data = self.get_field(row, "DATA")
            tipo = self.get_field(row, "TIPO")
            status_tesouraria = self.get_field(row, "STATUS DA TESOURARIA")
            doc_soma = self.get_field(row, "DOC. SOMA")
            finance = self.get_field(row, "FINANCE")
            valor = self.get_field(row, "VALOR DA COMPRA")

            if not self._is_valid_id(id_interno):
                return False, f"ID_INTERNO inválido: {id_interno or ''}"

            if not data:
                return False, "DATA vazia"

            if (tipo or "").upper() != "PAGAMENTO":
                return False, f"TIPO inválido: {tipo or ''}"

            if (status_tesouraria or "").casefold() != "concluído".casefold():
                return False, "STATUS DA TESOURARIA não está Concluído"

            if not doc_soma:
                return False, "DOC.SOMA está vazio"

            if finance:
                return False, "FINANCE não está vazio"

            if not valor:
                return False, "VALOR DA COMPRA vazio"

            try:
                amount = float(str(valor).replace(" ", "").replace(",", "."))
            except (TypeError, ValueError):
                return False, f"VALOR DA COMPRA inválido: {valor}"

            if amount <= 0:
                return False, f"VALOR DA COMPRA <= 0: {valor}"

            return True, None
        except Exception as error:
            logger.error(
                "Validation error on SAÍDAS row %s: %s",
                row_number,
                error,
            )
            return False, f"Erro na validação: {str(error)[:80]}"

    def get_field(self, row: list, field_name: str) -> Optional[str]:
        index = self.column_indices.get(field_name.upper().strip())
        if index is None or index >= len(row):
            return None

        value = row[index]
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @staticmethod
    def _is_valid_id(value: str | None) -> bool:
        if not value or len(value) != 13:
            return False
        return value[:3].upper() == "SAI" and value[3:].isdigit()
