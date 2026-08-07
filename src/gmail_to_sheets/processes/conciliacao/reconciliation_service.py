"""Serviço de conciliação que escreve DOC.SOMA na sheet de origem.

Atualiza registros em sheet de origem com DOC.SOMA obtido de CONTAORDEM.
"""

import logging
from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Serviço de conciliação para atualizar sheet de origem."""

    def __init__(self, sheets_client: SheetsClient, spreadsheet_id: str, source_sheet: str = "T_EXTRATO"):
        """
        Inicializa o serviço de conciliação.

        Args:
            sheets_client: Cliente Sheets autenticado
            spreadsheet_id: ID da planilha
            source_sheet: Nome da sheet de origem (padrão: T_EXTRATO)
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.column_indices = self._load_column_indices()
        self.batch_updates = []

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

    def add_update(self, row_number: int, doc_soma: str) -> None:
        """
        Adiciona uma atualização ao batch.

        Args:
            row_number: Número da linha para atualizar
            doc_soma: Valor de DOC.SOMA
        """
        doc_soma_idx = self.column_indices.get("DOC. SOMA", 0)
        col_letter = chr(ord('A') + doc_soma_idx)
        cell_address = f"{col_letter}{row_number}"
        range_name = f"{self.source_sheet}!{cell_address}"

        self.batch_updates.append({
            "range": range_name,
            "values": [[doc_soma]]
        })

        logger.debug(f"Agendada atualização: {range_name} = {doc_soma}")

    def apply_batch_updates(self) -> dict:
        """
        Aplica todas as atualizações em batch.

        Returns:
            Dict com resultados {'updated': int, 'failed': int}
        """
        if not self.batch_updates:
            logger.info("Nenhuma atualização para aplicar")
            return {"updated": 0, "failed": 0}

        try:
            logger.info(f"Aplicando {len(self.batch_updates)} atualizações...")

            request_body = {
                "data": self.batch_updates,
                "valueInputOption": "RAW"
            }

            response = self.sheets_client.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request_body
            ).execute()

            updated = len(self.batch_updates)
            logger.info(f"      Atualizadas: {updated} linhas")

            return {
                "updated": updated,
                "failed": 0,
                "response": response
            }

        except Exception as e:
            logger.error(f"Erro ao aplicar batch updates: {e}")
            return {
                "updated": 0,
                "failed": len(self.batch_updates)
            }

    def clear_batch(self) -> None:
        """Limpa o batch de atualizações."""
        self.batch_updates = []
