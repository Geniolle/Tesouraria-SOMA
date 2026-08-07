"""Validador para o processo de Conciliação.

Valida se uma linha na sheet de origem (T_EXTRATO) é candidata para conciliação:
- DOC.SOMA deve estar vazio
- ID_INTERNO deve estar preenchido
"""

import logging

logger = logging.getLogger(__name__)


class ConciliationValidator:
    """Valida registros para o processo de conciliação."""

    def __init__(self):
        """Inicializa o validador."""
        # Column indices for T_EXTRATO
        self.doc_soma_idx = 0  # DOC.SOMA (0-indexed, column 1)
        self.id_interno_idx = 8  # ID_INTERNO (0-indexed, column 9)

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
        # Validar DOC.SOMA vazio
        if self.doc_soma_idx < len(row) and row[self.doc_soma_idx]:
            doc_soma = str(row[self.doc_soma_idx]).strip()
            if doc_soma:
                return False, "DOC.SOMA já preenchido"

        # Validar ID_INTERNO preenchido
        if self.id_interno_idx >= len(row):
            return False, "ID_INTERNO ausente"

        id_interno = str(row[self.id_interno_idx]).strip() if row[self.id_interno_idx] else ""
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
        if self.id_interno_idx < len(row):
            return str(row[self.id_interno_idx]).strip()
        return ""
