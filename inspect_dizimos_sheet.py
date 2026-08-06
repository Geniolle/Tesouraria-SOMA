#!/usr/bin/env python
"""
Inspect DÍZIMOS/OFERTAS sheet to discover column structure.
"""

import logging
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def inspect_dizimos_sheet():
    """Inspect DÍZIMOS/OFERTAS sheet columns."""
    try:
        # Load configuration
        settings = load_settings()
        spreadsheet_id = settings.sheets.spreadsheet_id

        logger.info(f"Spreadsheet ID: {spreadsheet_id}")

        # Initialize Sheets client
        sheets_client = SheetsClient(
            service_account_path=str(settings.sheets.service_account_path)
        )

        # Get headers from DÍZIMOS/OFERTAS sheet
        logger.info("Fetching headers from DÍZIMOS/OFERTAS sheet...")
        headers = sheets_client.get_headers(spreadsheet_id, "DÍZIMOS/OFERTAS")

        if not headers:
            logger.error("No headers found in DÍZIMOS/OFERTAS sheet")
            return

        # Display results
        print("\n" + "="*80)
        print("COLUNA ESTRUTURA - SHEET: DÍZIMOS/OFERTAS")
        print("="*80 + "\n")

        print(f"Total de Colunas: {len(headers)}\n")
        print(f"{'Índice':<8} {'Nome da Coluna':<40} {'Preenchida':<15}")
        print("-" * 80)

        for idx, header in enumerate(headers, 1):
            header_str = str(header).strip() if header else "[VAZIA]"
            is_filled = "Sim" if header_str and header_str != "[VAZIA]" else "Não"
            print(f"{idx:<8} {header_str:<40} {is_filled:<15}")

        print("\n" + "="*80)
        print("COLUNAS PREENCHIDAS (resumo):\n")

        filled_columns = [(idx, str(h).strip()) for idx, h in enumerate(headers, 1) if h and str(h).strip()]
        for idx, name in filled_columns:
            print(f"  [{idx:2d}] {name}")

        print("\n" + "="*80 + "\n")

    except Exception as e:
        logger.error(f"Error inspecting sheet: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    inspect_dizimos_sheet()
