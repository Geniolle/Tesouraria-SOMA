"""Serviço de conciliação que escreve DOC.SOMA na sheet de origem.

Atualiza registros em T_EXTRATO com DOC.SOMA obtido de CONTAORDEM.
"""

import logging
from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Serviço de conciliação para atualizar T_EXTRATO."""

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
        self.doc_soma_idx = 10  # DOC.SOMA (0-indexed, coluna 11)
        self.batch_updates = []

    def add_update(self, row_number: int, doc_soma: str) -> None:
        """
        Adiciona uma atualização ao batch.

        Args:
            row_number: Número da linha para atualizar
            doc_soma: Valor de DOC.SOMA (7 dígitos numéricos)
        """
        # Column K = 11ª coluna (11 = K)
        col_letter = chr(ord('A') + self.doc_soma_idx)
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

    def update_single_cell(self, row_number: int, doc_soma: str) -> bool:
        """
        Atualiza uma única célula (operação imediata, não batch).

        Útil para testes ou atualização isolada.

        Args:
            row_number: Número da linha para atualizar
            doc_soma: Valor de DOC.SOMA (7 dígitos numéricos)

        Returns:
            True se bem-sucedido, False caso contrário
        """
        try:
            col_letter = chr(ord('A') + self.doc_soma_idx)
            cell_address = f"{col_letter}{row_number}"
            range_name = f"{self.source_sheet}!{cell_address}"

            request_body = {
                "data": [
                    {
                        "range": range_name,
                        "values": [[doc_soma]]
                    }
                ],
                "valueInputOption": "RAW"
            }

            response = self.sheets_client.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request_body
            ).execute()

            logger.debug(f"Atualizada célula: {range_name} = {doc_soma}")
            return True

        except Exception as e:
            logger.error(f"Erro ao atualizar célula: {e}")
            return False
