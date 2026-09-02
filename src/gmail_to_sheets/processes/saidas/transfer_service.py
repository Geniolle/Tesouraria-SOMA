"""Transfer validated SAÍDAS rows to CONTAORDEM."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.gmail_to_sheets.services.contaordem_sequence import build_descricao_soma

logger = logging.getLogger(__name__)


class SaidaTransferError(Exception):
    """Raised when a SAÍDAS transfer cannot be completed."""


class SaidaTransferService:
    """Map SAÍDAS fields into the CONTAORDEM schema."""

    source_sheet = "SAÍDAS"
    target_sheet = "CONTAORDEM"
    process_name = "SAÍDAS"
    target_type = "Saída"

    def __init__(
        self,
        sheets_client,
        spreadsheet_id: str,
        source_headers: list[str] | None = None,
        target_headers: list[str] | None = None,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id

        if source_headers is None:
            source_headers = sheets_client.get_headers(
                spreadsheet_id,
                self.source_sheet,
            )
        if target_headers is None:
            target_headers = sheets_client.get_headers(
                spreadsheet_id,
                self.target_sheet,
            )

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

    def build_target_row(
        self,
        source_row: list,
        sequence_number: int,
    ) -> list:
        row = [""] * len(self.target_headers)

        data = self._source(source_row, "DATA")
        data_valor = self._source(source_row, "DATA VALOR")
        descricao = self._source(source_row, "DESCRIÇÃO DA COMPRA")
        valor = self._source(source_row, "VALOR DA COMPRA")
        doc_soma = self._source(source_row, "DOC. SOMA")
        plano_conta = self._source(source_row, "PLANO DE CONTA")
        centro_custo = self._source(source_row, "CENTRO DE CUSTO")
        descricao_soma = self._source(source_row, "DESCRIÇÃO SOMA")
        forma_pagamento = self._source(source_row, "FORMA DE PAGAMENTO")
        caixa = self._source(source_row, "CAIXA")
        id_interno = self._source(source_row, "ID_INTERNO")

        mapping = {
            "DATA MOV.": data,
            "DATA VALOR": data_valor,
            "DESCRIÇÃO": descricao,
            "IMPORTÂNCIA": self._format_amount(valor),
            "DOC. SOMA": doc_soma,
            "TIPO": self.target_type,
            "PLANO DE CONTA": plano_conta,
            "CENTRO DE CUSTO": centro_custo,
            "DESCRIÇÃO SOMA": build_descricao_soma(
                descricao_soma or descricao,
                sequence_number,
            ),
            "FORMA DE PAGAMENTO": self._target_payment_method(forma_pagamento),
            "CAIXA": caixa,
            "PERÍODO": self._month(data),
            "PROCESSO": self.process_name,
            "ID_INTERNO": id_interno,
        }

        for field, value in mapping.items():
            index = self.target_indices.get(field.upper())
            if index is not None and index < len(row):
                row[index] = value or ""

        return row

    def append(self, target_row: list) -> bool:
        try:
            return bool(
                self.sheets_client.append_rows(
                    self.spreadsheet_id,
                    self.target_sheet,
                    [target_row],
                )
            )
        except Exception as error:
            raise SaidaTransferError(str(error)) from error

    def sort_by_date(self) -> None:
        """Sort CONTAORDEM by DATA MOV. descending."""
        self.sheets_client.sort_contaordem_by_data_mov(
            self.spreadsheet_id
        )

    def _source(self, row: list, field: str) -> Optional[str]:
        index = self.source_indices.get(field.upper())
        if index is None or index >= len(row):
            return None

        value = row[index]
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @staticmethod
    def _format_amount(value: str | None) -> str:
        if not value:
            return "0,00"

        try:
            amount = float(str(value).replace(" ", "").replace(",", "."))
            return f"{amount:.2f}".replace(".", ",")
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _target_payment_method(source_method: str | None) -> str:
        """Map the source FORMA DE PAGAMENTO to the CONTAORDEM value.

        - ``DINHEIRO`` (substring, case-insensitive) stays ``DINHEIRO``
        - empty stays empty
        - anything else becomes ``TRANSFERÊNCIA BANCÁRIA``
        """
        method = (source_method or "").strip()

        if not method:
            return ""

        if "DINHEIRO" in method.upper():
            return "DINHEIRO"

        return "TRANSFERÊNCIA BANCÁRIA"

    @staticmethod
    def _month(value: str | None) -> str:
        if not value:
            return ""

        try:
            month = datetime.strptime(value, "%d/%m/%Y").month
        except ValueError:
            return ""

        months = [
            "JANEIRO",
            "FEVEREIRO",
            "MARÇO",
            "ABRIL",
            "MAIO",
            "JUNHO",
            "JULHO",
            "AGOSTO",
            "SETEMBRO",
            "OUTUBRO",
            "NOVEMBRO",
            "DEZEMBRO",
        ]
        return months[month - 1]
