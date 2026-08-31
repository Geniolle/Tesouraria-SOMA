"""Map a Verbo Café source row into the CONTAORDEM schema and append it."""

from __future__ import annotations

import logging
from typing import Optional

from ._format import (
    format_amount_pt,
    format_date_ddmmyyyy,
    month_name_pt,
)
from .config import TARGET_SHEET, VerboCafePhase

logger = logging.getLogger(__name__)


class VerboCafeTransferError(Exception):
    """Raised when a Verbo Café transfer cannot be completed."""


class VerboCafeTransferService:
    """Build and append CONTAORDEM rows for one Verbo Café phase."""

    target_sheet = TARGET_SHEET

    def __init__(
        self,
        sheets_client,
        target_spreadsheet_id: str,
        source_headers: list[str],
        target_headers: list[str],
        phase: VerboCafePhase,
    ) -> None:
        self.sheets_client = sheets_client
        self.target_spreadsheet_id = target_spreadsheet_id
        self.phase = phase
        self.source_headers = source_headers
        self.target_headers = target_headers
        self.source_indices = self._indices(source_headers)
        self.target_indices = self._indices(target_headers)

    @staticmethod
    def _indices(headers: list[str]) -> dict[str, int]:
        return {
            str(header).upper().strip(): index
            for index, header in enumerate(headers)
            if header
        }

    def build_target_row(self, source_row: list, sequence_number: int) -> list:
        row = [""] * len(self.target_headers)

        data_mov = format_date_ddmmyyyy(
            self._source(source_row, self.phase.data_field)
        )
        tipo_origem = self._source(source_row, self.phase.tipo_field) or ""
        id_interno = self._source(source_row, self.phase.id_field) or ""
        descricao = f"{tipo_origem} {id_interno}".strip()
        valor = self._source(source_row, self.phase.amount_field)
        descricao_soma = f"{self.phase.desc_soma_base} N{sequence_number:03d}"

        mapping = {
            "DATA MOV.": data_mov or "",
            "DESCRIÇÃO": descricao,
            "IMPORTÂNCIA": format_amount_pt(valor),
            "TIPO": self.phase.target_type,
            "PLANO DE CONTA": self.phase.plano_conta,
            "CENTRO DE CUSTO": self.phase.centro_custo,
            "DESCRIÇÃO SOMA": descricao_soma,
            "FORMA DE PAGAMENTO": self.phase.forma_pagamento,
            "CAIXA": self.phase.caixa,
            "PERÍODO": month_name_pt(data_mov),
            "PROCESSO": self.phase.processo_tag,
            "ID_INTERNO": id_interno,
        }

        for field, value in mapping.items():
            index = self.target_indices.get(field.upper())
            if index is not None and index < len(row):
                row[index] = value if value is not None else ""

        return row

    def append(self, target_row: list) -> bool:
        try:
            return bool(
                self.sheets_client.append_rows(
                    self.target_spreadsheet_id,
                    self.target_sheet,
                    [target_row],
                )
            )
        except Exception as error:  # noqa: BLE001
            raise VerboCafeTransferError(str(error)) from error

    def _source(self, row: list, field: str) -> Optional[str]:
        index = self.source_indices.get(field.upper())
        if index is None or index >= len(row):
            return None
        value = row[index]
        if value is None:
            return None
        text = str(value).strip()
        return text or None
