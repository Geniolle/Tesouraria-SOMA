"""Orquestrador do Processo de Conciliação.

Coordena o pipeline completo de conciliação:
1. Pesquisar linhas em T_EXTRATO com DOC.SOMA vazio
2. Validar ID_INTERNO preenchido
3. Pesquisar ID_INTERNO em CONTAORDEM
4. Se DOC.SOMA existe em CONTAORDEM, copiar para T_EXTRATO
5. Validar formato de DOC.SOMA (7 dígitos numéricos)
"""

import logging

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.conciliacao.validator import ConciliationValidator
from src.gmail_to_sheets.processes.conciliacao.lookup_service import LookupService
from src.gmail_to_sheets.processes.conciliacao.reconciliation_service import (
    ReconciliationService,
)

logger = logging.getLogger(__name__)


class ConciliationOrchestrator:
    """Orquestrador principal do processo de conciliação."""

    def __init__(self, source_sheet: str = "T_EXTRATO"):
        """
        Inicializa o orquestrador.

        Args:
            source_sheet: Sheet de origem (padrão: T_EXTRATO)
        """
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.sheets_client: SheetsClient | None = None
        self.spreadsheet_id = self.settings.sheets.spreadsheet_id
        self.source_sheet = source_sheet

    def run(self) -> None:
        """Executa o pipeline completo de conciliação."""
        try:
            logger.info("=" * 80)
            logger.info(f"Iniciando processo de Conciliação ({self.source_sheet})")
            logger.info("=" * 80)

            # Phase 1: Authenticate
            self._authenticate_sheets()

            # Phase 2: Load and validate candidates
            candidates = self._load_and_validate_candidates()
            if not candidates:
                logger.warning("Nenhum registro candidato para conciliação")
                return

            logger.info(f"Encontrados {len(candidates)} registros candidatos")

            # Phase 3: Load CONTAORDEM cache
            self._load_reference_data()

            # Phase 4: Lookup and reconcile
            reconciliation_result = self._perform_reconciliation(candidates)

            logger.info("=" * 80)
            logger.info("Processo de Conciliação concluído!")
            logger.info(f"  - Candidatos encontrados: {len(candidates)}")
            logger.info(f"  - Registros conciliados: {reconciliation_result['reconciled']}")
            logger.info(f"  - Sem correspondência: {reconciliation_result['not_found']}")
            logger.info(f"  - Formato inválido: {reconciliation_result['invalid_format']}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Pipeline falhou: {e}", exc_info=True)
            raise

    def _authenticate_sheets(self) -> None:
        """Autentica com Google Sheets API."""
        try:
            logger.info("[1/4] Autenticando com Google Sheets...")
            self.sheets_client = SheetsClient(
                service_account_path=str(self.settings.sheets.service_account_path)
            )
            logger.info("      Sheets autenticado")
        except Exception as e:
            logger.error(f"Falha na autenticação: {e}")
            raise

    def _load_and_validate_candidates(self) -> list:
        """Carrega e valida registros candidatos para conciliação."""
        if not self.sheets_client:
            raise RuntimeError("Cliente Sheets não inicializado")

        try:
            logger.info(f"[2/4] Carregando e validando registros de {self.source_sheet}...")

            validator = ConciliationValidator()

            # Load data
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.source_sheet}!A2:Z99999",
            ).execute()

            rows = result.get("values", [])
            logger.info(f"      Carregadas {len(rows)} linhas")

            candidates = []

            for row_num, row in enumerate(rows, start=2):
                is_candidate, error = validator.is_candidate_for_reconciliation(row, row_num)

                if is_candidate:
                    id_interno = validator.extract_search_key(row)
                    candidates.append({
                        "row_number": row_num,
                        "row_data": row,
                        "id_interno": id_interno
                    })
                else:
                    logger.debug(f"Linha {row_num} descartada: {error}")

            logger.info(f"      Candidatos válidos: {len(candidates)}")
            return candidates

        except Exception as e:
            logger.error(f"Erro ao carregar/validar: {e}")
            raise

    def _load_reference_data(self) -> None:
        """Carrega dados de referência (CONTAORDEM)."""
        if not self.sheets_client:
            raise RuntimeError("Cliente Sheets não inicializado")

        try:
            logger.info("[3/4] Carregando dados de referência...")

            self.lookup_service = LookupService(self.sheets_client, self.spreadsheet_id)
            self.lookup_service.load_contaordem_data()

            logger.info("      Dados de referência carregados")

        except Exception as e:
            logger.error(f"Erro ao carregar referência: {e}")
            raise

    def _perform_reconciliation(self, candidates: list) -> dict:
        """Realiza a conciliação dos registros."""
        if not self.sheets_client:
            raise RuntimeError("Cliente Sheets não inicializado")

        try:
            logger.info("[4/4] Realizando conciliação...")

            reconciliation_svc = ReconciliationService(
                self.sheets_client, self.spreadsheet_id, self.source_sheet
            )

            reconciled = 0
            not_found = 0
            invalid_format = 0

            for candidate in candidates:
                row_num = candidate["row_number"]
                id_interno = candidate["id_interno"]

                # Lookup in CONTAORDEM
                lookup_result = self.lookup_service.lookup_doc_soma(id_interno)

                if not lookup_result["found"]:
                    logger.debug(f"Linha {row_num}: ID_INTERNO {id_interno} não encontrado")
                    not_found += 1
                    continue

                doc_soma = lookup_result["doc_soma"]

                # Validate format
                if not self.lookup_service.validate_doc_soma_format(doc_soma):
                    logger.debug(f"Linha {row_num}: DOC.SOMA inválido: {doc_soma}")
                    invalid_format += 1
                    continue

                # Add to batch update
                reconciliation_svc.add_update(row_num, doc_soma)
                logger.debug(f"Linha {row_num}: Agendada atualização com DOC.SOMA={doc_soma}")
                reconciled += 1

            # Apply batch updates
            if reconciliation_svc.batch_updates:
                result = reconciliation_svc.apply_batch_updates()
                logger.info(f"      Atualizadas {result['updated']} linhas em batch")

            logger.info(f"      Conciliados: {reconciled}")
            return {
                "reconciled": reconciled,
                "not_found": not_found,
                "invalid_format": invalid_format
            }

        except Exception as e:
            logger.error(f"Erro na conciliação: {e}")
            raise


def run_conciliation_process(source_sheet: str = "T_EXTRATO"):
    """Ponto de entrada para o processo de conciliação."""
    orchestrator = ConciliationOrchestrator(source_sheet)
    orchestrator.run()


if __name__ == "__main__":
    run_conciliation_process()
