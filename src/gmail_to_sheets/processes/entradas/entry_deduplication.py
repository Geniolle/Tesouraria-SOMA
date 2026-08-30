"""Read-only CONTAORDEM deduplication by business key and ID_INTERNO."""

from __future__ import annotations

import logging

from src.gmail_to_sheets.clients.sheets_projection import read_projected_rows

logger = logging.getLogger(__name__)


class EntryDeduplicationService:
    """Check duplicate entries before transferring into CONTAORDEM."""

    target_sheet = "CONTAORDEM"

    def __init__(
        self,
        sheets_client,
        spreadsheet_id: str,
        headers: list[str] | None = None,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.existing_keys: set[str] = set()
        self.existing_ids: set[str] = set()

        if headers is None:
            headers = self.sheets_client.get_headers(
                self.spreadsheet_id,
                self.target_sheet,
            )

        self.column_indices = {
            str(header).upper().strip(): index
            for index, header in enumerate(headers)
            if header
        }
        self._load_existing_entries()

    def _load_existing_entries(self) -> None:
        """Load only fields required for duplicate detection."""
        try:
            rows = read_projected_rows(
                self.sheets_client,
                self.spreadsheet_id,
                self.target_sheet,
                self.column_indices,
                [
                    "DATA MOV.",
                    "IMPORTÂNCIA",
                    "DESCRIÇÃO",
                    "ID_INTERNO",
                ],
            )

            data_idx = self.column_indices["DATA MOV."]
            valor_idx = self.column_indices["IMPORTÂNCIA"]
            desc_idx = self.column_indices["DESCRIÇÃO"]
            id_idx = self.column_indices["ID_INTERNO"]

            for _, row in rows:
                id_interno = self._row_value(row, id_idx)
                if id_interno:
                    self.existing_ids.add(id_interno)

                data = self._row_value(row, data_idx)
                valor = self._row_value(row, valor_idx)
                descricao = self._row_value(row, desc_idx)
                if data and valor and descricao:
                    self.existing_keys.add(
                        self._normalize_key(data, valor, descricao)
                    )

            logger.info(
                "Loaded %s business keys and %s IDs from CONTAORDEM",
                len(self.existing_keys),
                len(self.existing_ids),
            )
        except Exception as error:
            logger.error(
                "Failed to load CONTAORDEM deduplication data: %s",
                error,
            )
            raise

    def is_duplicate(
        self,
        data: str,
        valor: str,
        descricao: str,
        id_interno: str | None = None,
    ) -> bool:
        """Return True if ID or data+value+description already exists."""
        if id_interno and str(id_interno).strip() in self.existing_ids:
            return True

        key = self._normalize_key(data, valor, descricao)
        return key in self.existing_keys

    def register_new_entry(
        self,
        data: str,
        valor: str,
        descricao: str,
        id_interno: str | None = None,
    ) -> None:
        """Register an entry locally to protect the current batch."""
        self.existing_keys.add(
            self._normalize_key(data, valor, descricao)
        )
        if id_interno:
            self.existing_ids.add(str(id_interno).strip())

    @staticmethod
    def _row_value(row: list, index: int) -> str:
        if index >= len(row) or row[index] is None:
            return ""
        return str(row[index]).strip()

    @staticmethod
    def _normalize_key(
        data: str,
        valor: str,
        descricao: str,
    ) -> str:
        data_norm = str(data).strip()

        valor_norm = (
            str(valor)
            .strip()
            .replace(" ", "")
            .replace(",", ".")
        )
        try:
            valor_norm = f"{float(valor_norm):.2f}"
        except (ValueError, TypeError):
            pass

        descricao_norm = " ".join(
            str(descricao).strip().casefold().split()
        )
        return f"{data_norm}|{valor_norm}|{descricao_norm}"
