#!/usr/bin/env python3
"""
Teste do processo de Conciliação.

Valida:
- Validação de candidatos (DOC.SOMA vazio + ID_INTERNO preenchido)
- Lookup em CONTAORDEM
- Validação de formato DOC.SOMA
- Batch updates em T_EXTRATO
"""

import logging
from src.gmail_to_sheets.processes.conciliacao.orchestrator import ConciliationOrchestrator

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_conciliation_process():
    """Testa o processo completo de conciliação."""
    logger.info("=" * 80)
    logger.info("TESTE: Processo de Conciliação")
    logger.info("=" * 80)

    try:
        orchestrator = ConciliationOrchestrator(source_sheet="T_EXTRATO")
        orchestrator.run()

        logger.info("=" * 80)
        logger.info("TESTE PASSOU: Processo de conciliação executado com sucesso")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"TESTE FALHOU: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    test_conciliation_process()
