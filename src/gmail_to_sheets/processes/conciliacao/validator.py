"""Validador para o processo de Conciliação.

Valida se uma linha na sheet de origem é candidata para conciliação:
- DOC.SOMA deve estar vazio
- ID_INTERNO deve estar preenchido
"""

import logging

logger = logging.getLogger(__name__)


class ConciliationValidator:
    """Valida registros para o processo de conciliação."""

    def __init__(
        self,
        sheets_client,
        spreadsheet_id: str,
        source_sheet: str = "T_EXTRATO",
        headers: list[str] | None = None,
    ):
        """Inicializa o validador.

        Args:
            sheets_client: Cliente autenticado de Sheets
            spreadsheet_id: ID da planilha
            source_sheet: Sheet de origem
            headers: Cabeçalho opcional previamente carregado
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.column_indices = self._load_column_indices(headers=headers)

    def _load_column_indices(self, headers: list[str] | None = None) -> dict:
        """Carrega índices de colunas dinamicamente da header."""
        try:
            if headers is None:
                headers = self.sheets_client.get_headers(
                    self.spreadsheet_id, self.source_sheet
                )
            indices = {}

            for idx, header in enumerate(headers):
                header_name = str(header).upper().strip() if header else ""
                indices[header_name] = idx

            logger.info(
                f"Carregados {len(indices)} campos de {self.source_sheet}"
            )
            return indices

        except Exception as e:
            logger.error(f"Erro ao carregar campos de {self.source_sheet}: {e}")
            raise

    def is_candidate_for_reconciliation(
        self, row: list, row_num: int
    ) -> tuple[bool, str]:
        """Valida se uma linha é candidata para conciliação."""
        doc_soma_idx = self.column_indices.get("DOC. SOMA")
        id_interno_idx = self.column_indices.get("ID_INTERNO")

        if doc_soma_idx is None:
            return False, "DOC.SOMA ausente"
        if id_interno_idx is None:
            return False, "ID_INTERNO ausente"

        if doc_soma_idx < len(row) and row[doc_soma_idx]:
            doc_soma = str(row[doc_soma_idx]).strip()
            if doc_soma:
                return False, "DOC.SOMA já preenchido"

        if id_interno_idx >= len(row):
            return False, "ID_INTERNO ausente"

        id_interno = (
            str(row[id_interno_idx]).strip() if row[id_interno_idx] else ""
        )
        if not id_interno:
            return False, "ID_INTERNO vazio"

        if not self._is_valid_id_format(id_interno):
            return False, f"ID_INTERNO formato inválido: {id_interno}"

        return True, ""

    def _is_valid_id_format(self, id_interno: str) -> bool:
        """Valida formato de ID_INTERNO: 3 letras + 10 dígitos."""
        if len(id_interno) != 13:
            return False

        if not id_interno[:3].isalpha():
            return False

        if not id_interno[3:].isdigit():
            return False

        return True

    def extract_search_key(self, row: list) -> str:
        """Extrai a chave de busca (ID_INTERNO) de uma linha."""
        id_interno_idx = self.column_indices.get("ID_INTERNO")
        if id_interno_idx is not None and id_interno_idx < len(row):
            return str(row[id_interno_idx]).strip()
        return ""
