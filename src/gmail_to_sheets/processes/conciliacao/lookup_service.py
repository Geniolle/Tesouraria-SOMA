"""Serviço de lookup para pesquisar DOC.SOMA em CONTAORDEM.

Pesquisa linhas em CONTAORDEM usando o ID_INTERNO como chave.
"""

import logging

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class LookupService:
    """Serviço de lookup em CONTAORDEM."""

    def __init__(self, sheets_client: SheetsClient, spreadsheet_id: str):
        """
        Inicializa o serviço de lookup.

        Args:
            sheets_client: Cliente Sheets autenticado
            spreadsheet_id: ID da planilha
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.contaordem_cache: dict[str, dict] = {}
        self.column_indices = self._load_column_indices()

    def _load_column_indices(self) -> dict:
        """Carrega índices de colunas dynamicamente da header."""
        try:
            headers = self.sheets_client.get_headers(self.spreadsheet_id, "CONTAORDEM")
            indices = {}

            for idx, header in enumerate(headers):
                header_name = str(header).upper().strip() if header else ""
                indices[header_name] = idx

            logger.info(f"Carregados {len(indices)} campos de CONTAORDEM")
            return indices

        except Exception as e:
            logger.error(f"Erro ao carregar campos de CONTAORDEM: {e}")
            raise

    def load_contaordem_data(self) -> None:
        """Carrega todos os dados de CONTAORDEM em cache."""
        try:
            logger.info("Carregando dados de CONTAORDEM...")

            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=self.sheets_client.get_data_range(self.spreadsheet_id, "CONTAORDEM"),
            ).execute()

            rows = result.get("values", [])
            logger.info(f"      Carregadas {len(rows)} linhas de CONTAORDEM")

            # Encontrar índices
            id_interno_idx = self.column_indices.get("ID_INTERNO")
            doc_soma_idx = self.column_indices.get("DOC. SOMA")
            if id_interno_idx is None:
                raise RuntimeError("Coluna ID_INTERNO não encontrada em CONTAORDEM")
            if doc_soma_idx is None:
                raise RuntimeError("Coluna DOC. SOMA não encontrada em CONTAORDEM")

            # Indexar por ID_INTERNO para lookup rápido
            for row_num, row in enumerate(rows, start=2):
                if id_interno_idx < len(row):
                    id_interno = str(row[id_interno_idx]).strip() if row[id_interno_idx] else ""
                    if id_interno:
                        doc_soma = str(row[doc_soma_idx]).strip() if doc_soma_idx < len(row) and row[doc_soma_idx] else ""
                        self.contaordem_cache[id_interno] = {
                            "row_number": row_num,
                            "row_data": row,
                            "doc_soma": doc_soma
                        }

            logger.info(f"      Cache construído com {len(self.contaordem_cache)} registros indexados")

        except Exception as e:
            logger.error(f"Erro ao carregar CONTAORDEM: {e}")
            raise

    def lookup_doc_soma(self, id_interno: str) -> dict | None:
        """
        Pesquisa DOC.SOMA em CONTAORDEM usando ID_INTERNO.

        Args:
            id_interno: ID_INTERNO para pesquisar

        Returns:
            Dict com {'found': bool, 'doc_soma': str}
        """
        if id_interno in self.contaordem_cache:
            cached = self.contaordem_cache[id_interno]
            doc_soma = cached["doc_soma"]

            if doc_soma:
                return {
                    "found": True,
                    "doc_soma": doc_soma,
                    "row_number": cached["row_number"]
                }

        return {"found": False, "doc_soma": None}
