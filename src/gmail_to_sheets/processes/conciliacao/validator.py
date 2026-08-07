"""Validador para o processo de Conciliação.

Valida se uma linha na sheet de origem é candidata para conciliação:
- DOC.SOMA deve estar vazio
- ID_INTERNO deve estar preenchido
"""

import logging

logger = logging.getLogger(__name__)


class ConciliationValidator:
    """Valida registros para o processo de conciliação."""

    def __init__(self, sheets_client, spreadsheet_id: str, source_sheet: str = "T_EXTRATO"):
        """
        Inicializa o validador.

        Args:
            sheets_client: Cliente autenticado de Sheets
            spreadsheet_id: ID da planilha
            source_sheet: Sheet de origem
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.column_indices = self._load_column_indices()

    def _load_column_indices(self) -> dict:
        """Carrega índices de colunas dynamicamente da header."""
        try:
            headers = self.sheets_client.get_headers(self.spreadsheet_id, self.source_sheet)
            indices = {}

            for idx, header in enumerate(headers):
                header_name = str(header).upper().strip() if header else ""
                indices[header_name] = idx

            logger.info(f"Carregados {len(indices)} campos de {self.source_sheet}")
            return indices

        except Exception as e:
            logger.error(f"Erro ao carregar campos de {self.source_sheet}: {e}")
            raise

    def is_candidate_for_reconciliation(self, row: list, row_num: int) -> tuple[bool, str]:
        """
        Valida se uma linha é candidata para conciliação.

        Critérios:
        - DOC.SOMA deve estar vazio
        - ID_INTERNO deve estar preenchido

        Args:
            row: Dados da linha
            row_num: Número da linha (para logging)

        Returns:
            Tupla (is_valid, error_message)
        """
        # Encontrar índices de colunas
        doc_soma_idx = self.column_indices.get("DOC. SOMA", 0)
        id_interno_idx = self.column_indices.get("ID_INTERNO", 8)

        # Validar DOC.SOMA vazio
        if doc_soma_idx < len(row) and row[doc_soma_idx]:
            doc_soma = str(row[doc_soma_idx]).strip()
            if doc_soma:
                return False, "DOC.SOMA já preenchido"

        # Validar ID_INTERNO preenchido
        if id_interno_idx >= len(row):
            return False, "ID_INTERNO ausente"

        id_interno = str(row[id_interno_idx]).strip() if row[id_interno_idx] else ""
        if not id_interno:
            return False, "ID_INTERNO vazio"

        return True, ""

    def extract_search_key(self, row: list) -> str:
        """
        Extrai a chave de busca (ID_INTERNO) de uma linha.

        Args:
            row: Dados da linha

        Returns:
            ID_INTERNO
        """
        id_interno_idx = self.column_indices.get("ID_INTERNO", 8)
        if id_interno_idx < len(row):
            return str(row[id_interno_idx]).strip()
        return ""
