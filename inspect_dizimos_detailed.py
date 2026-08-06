#!/usr/bin/env python
"""
Detailed inspection of DÍZIMOS/OFERTAS sheet with sample data.
"""

import logging
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def inspect_dizimos_detailed():
    """Inspect DÍZIMOS/OFERTAS sheet with sample data."""
    try:
        # Load configuration
        settings = load_settings()
        spreadsheet_id = settings.sheets.spreadsheet_id

        # Initialize Sheets client
        sheets_client = SheetsClient(
            service_account_path=str(settings.sheets.service_account_path)
        )

        # Get headers and sample data
        logger.info("Fetching data from DÍZIMOS/OFERTAS sheet...")

        result = sheets_client.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="DÍZIMOS/OFERTAS!A1:Z5",  # Header + 4 sample rows
        ).execute()

        rows = result.get("values", [])

        if not rows:
            logger.error("No data found")
            return

        print("\n" + "="*100)
        print("ESTRUTURA DETALHADA - SHEET: DÍZIMOS/OFERTAS")
        print("="*100 + "\n")

        # Print headers
        headers = rows[0] if rows else []
        print(f"Total de Colunas: {len(headers)}\n")
        print("MAPEAMENTO DE COLUNAS:")
        print("-" * 100)
        print(f"{'Idx':<5} {'Nome':<35} {'Tipo de Dados (amostra)':<60}")
        print("-" * 100)

        for idx, header in enumerate(headers, 1):
            # Get sample value from first data row
            sample_value = ""
            if len(rows) > 1 and idx <= len(rows[1]):
                sample_value = str(rows[1][idx - 1])[:50] if rows[1][idx - 1] else "[vazio]"

            header_name = str(header).strip() if header else "[VAZIA]"
            print(f"{idx:<5} {header_name:<35} {sample_value:<60}")

        print("\n" + "="*100)
        print("DADOS DE AMOSTRA (primeiras 4 linhas de dados):\n")

        # Print sample data
        for row_num, row in enumerate(rows[1:], 1):
            print(f"Linha {row_num}:")
            for col_num, cell in enumerate(row, 1):
                if col_num <= len(headers):
                    header = headers[col_num - 1]
                    value = str(cell) if cell else "[vazio]"
                    print(f"  [{col_num:2d}] {header:<35} = {value}")
            print()

        print("="*100 + "\n")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    inspect_dizimos_detailed()
