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
        self.id_interno_idx = 16  # ID_INTERNO em CONTAORDEM (0-indexed, coluna 17)
        self.doc_soma_idx = 4  # DOC.SOMA em CONTAORDEM (0-indexed, coluna 5)

    def load_contaordem_data(self) -> None:
        """Carrega todos os dados de CONTAORDEM em cache."""
        try:
            logger.info("Carregando dados de CONTAORDEM...")

            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="CONTAORDEM!A2:Z99999",
            ).execute()

            rows = result.get("values", [])
            logger.info(f"      Carregadas {len(rows)} linhas de CONTAORDEM")

            # Indexar por ID_INTERNO para lookup rápido
            for row_num, row in enumerate(rows, start=2):
                if self.id_interno_idx < len(row):
                    id_interno = str(row[self.id_interno_idx]).strip()
                    if id_interno:
                        self.contaordem_cache[id_interno] = {
                            "row_number": row_num,
                            "row_data": row,
                            "doc_soma": self._extract_doc_soma(row)
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
            Dict com {'found': bool, 'doc_soma': str} ou None
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

    def _extract_doc_soma(self, row: list) -> str:
        """
        Extrai DOC.SOMA de uma linha.

        Args:
            row: Dados da linha

        Returns:
            DOC.SOMA ou string vazia
        """
        if self.doc_soma_idx < len(row):
            doc_soma = str(row[self.doc_soma_idx]).strip() if row[self.doc_soma_idx] else ""
            return doc_soma
        return ""

    def validate_doc_soma_format(self, doc_soma: str) -> bool:
        """
        Valida se DOC.SOMA está no formato correto (7 dígitos numéricos).

        Args:
            doc_soma: DOC.SOMA para validar

        Returns:
            True se válido, False caso contrário
        """
        if not doc_soma:
            return False

        # Remove espaços
        doc_soma = doc_soma.strip()

        # Verifica se é numérico e tem 7 caracteres
        if len(doc_soma) == 7 and doc_soma.isdigit():
            return True

        logger.warning(f"DOC.SOMA inválido: '{doc_soma}' (esperado: 7 dígitos numéricos)")
        return False
