"""Validation rules for Verbo Café source rows before transfer to CONTAORDEM."""

from __future__ import annotations

import logging
from typing import Optional

from ._format import parse_date, strip_accents_upper, to_number
from .config import (
    CASH_PAYMENT_METHOD,
    STATUS_FIELD,
    STATUS_OPEN,
    VerboCafePhase,
)

logger = logging.getLogger(__name__)


class VerboCafeValidatorError(Exception):
    """Raised when Verbo Café validation cannot be initialized."""


class VerboCafeValidator:
    """Validate a single source row for one Verbo Café phase.

    A row is eligible when:

    - ``STATUS DA TESOURARIA`` is ``EM ABERTO`` (accent/case-insensitive)
    - the phase's payment-method filter passes (``FORMA DE PAGAMENTO`` is
      ``DINHEIRO`` for the sales phase; payments have no such column)
    - ``DATA`` is present and parseable
    - the phase's amount column is greater than zero
    - ``ID_INTERNO`` is present
    """

    def __init__(
        self,
        phase: VerboCafePhase,
        headers: list[str],
    ) -> None:
        self.phase = phase
        self.column_indices = {
            str(header).upper().strip(): index
            for index, header in enumerate(headers)
            if header
        }
        missing = [
            header
            for header in phase.required_headers
            if header.upper().strip() not in self.column_indices
        ]
        if missing:
            raise VerboCafeValidatorError(
                f"{phase.source_sheet}: cabeçalhos em falta: {', '.join(missing)}"
            )

    def is_valid_entry(
        self,
        row: list,
        row_number: int,
    ) -> tuple[bool, Optional[str]]:
        try:
            status = self.get_field(row, STATUS_FIELD)
            if strip_accents_upper(status) != strip_accents_upper(STATUS_OPEN):
                return False, f"STATUS != EM ABERTO: {status or ''}"

            if self.phase.filter_cash:
                forma = self.get_field(row, "FORMA DE PAGAMENTO")
                if strip_accents_upper(forma) != strip_accents_upper(
                    CASH_PAYMENT_METHOD
                ):
                    return False, f"FORMA != DINHEIRO: {forma or ''}"

            data = self.get_field(row, self.phase.data_field)
            if not data or parse_date(data) is None:
                return False, f"DATA inválida: {data or ''}"

            if not self.get_field(row, self.phase.id_field):
                return False, "ID_INTERNO vazio"

            valor_raw = self.get_field(row, self.phase.amount_field)
            if not valor_raw:
                return False, f"{self.phase.amount_field} vazio"
            if to_number(valor_raw) <= 0:
                return False, f"{self.phase.amount_field} <= 0: {valor_raw}"

            return True, None
        except Exception as error:  # noqa: BLE001 - defensive per-row guard
            logger.error(
                "Validation error on %s row %s: %s",
                self.phase.source_sheet,
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

    def build_descricao(self, row: list) -> str:
        """CONTAORDEM ``DESCRIÇÃO`` = ``"<TIPO> <ID_INTERNO>"`` (trimmed)."""
        tipo = self.get_field(row, self.phase.tipo_field) or ""
        id_interno = self.get_field(row, self.phase.id_field) or ""
        return f"{tipo} {id_interno}".strip()
