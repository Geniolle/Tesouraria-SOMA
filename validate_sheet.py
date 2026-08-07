#!/usr/bin/env python
"""
Validate DÍZIMOS/OFERTAS sheet for documents ready to transfer.
Shows statistics and list of entries ready for processing.
"""

import logging
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.processes.entradas.entry_validator import EntryValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_sheet():
    """Validate DÍZIMOS/OFERTAS sheet."""
    try:
        # Load configuration
        settings = load_settings()
        sheets_client = SheetsClient(
            service_account_path=str(settings.sheets.service_account_path)
        )
        spreadsheet_id = settings.sheets.spreadsheet_id

        print("\n" + "=" * 80)
        print("VALIDAÇÃO - SHEET DÍZIMOS/OFERTAS")
        print("=" * 80 + "\n")

        # Load data
        result = sheets_client.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="DÍZIMOS/OFERTAS!A1:Z1000",
        ).execute()

        rows = result.get("values", [])
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        print(f"Total de linhas: {len(data_rows)}")
        print(f"Total de colunas: {len(headers)}\n")

        # Initialize validator
        validator = EntryValidator(sheets_client, spreadsheet_id)

        # Analyze
        valid_entries = []
        invalid_entries = []

        print("Analisando registros...")
        print("-" * 80)

        for row_num, row in enumerate(data_rows, start=2):
            is_valid, error = validator.is_valid_entry(row, row_num)

            if is_valid:
                valid_entries.append({
                    "row": row_num,
                    "data": row
                })
            else:
                invalid_entries.append({
                    "row": row_num,
                    "error": error
                })

        # Get column indices for display
        headers_upper = [str(h).upper() for h in headers]
        data_idx = headers_upper.index("DATA") if "DATA" in headers_upper else -1
        tipo_idx = headers_upper.index("TIPO") if "TIPO" in headers_upper else -1
        valor_idx = headers_upper.index("VALOR") if "VALOR" in headers_upper else -1
        finance_idx = headers_upper.index("FINANCE") if "FINANCE" in headers_upper else -1
        doc_soma_idx = headers_upper.index("DOC. SOMA") if "DOC. SOMA" in headers_upper else -1
        id_idx = headers_upper.index("ID_INTERNO") if "ID_INTERNO" in headers_upper else -1

        # Display results
        print("\n" + "=" * 80)
        print("RESULTADO DA VALIDAÇÃO")
        print("=" * 80 + "\n")

        print(f"Registros VALIDOS (podem ser enviados):  {len(valid_entries)}")
        print(f"Registros INVALIDOS (serao pulados):    {len(invalid_entries)}\n")

        if valid_entries:
            print("REGISTROS PRONTOS PARA TRANSFERÊNCIA:")
            print("-" * 80)
            print(f"{'Linha':<6} {'Data':<12} {'Tipo':<20} {'Valor':<10} {'Finance':<15} {'ID':<15}")
            print("-" * 80)

            for entry in valid_entries:
                row_num = entry["row"]
                row_data = entry["data"]

                data = str(row_data[data_idx]).strip() if data_idx >= 0 and data_idx < len(row_data) else "N/A"
                tipo = str(row_data[tipo_idx]).strip() if tipo_idx >= 0 and tipo_idx < len(row_data) else "N/A"
                valor = str(row_data[valor_idx]).strip() if valor_idx >= 0 and valor_idx < len(row_data) else "N/A"
                finance = str(row_data[finance_idx]).strip() if finance_idx >= 0 and finance_idx < len(row_data) else "N/A"
                id_interno = str(row_data[id_idx]).strip() if id_idx >= 0 and id_idx < len(row_data) else "N/A"

                print(f"{row_num:<6} {data:<12} {tipo[:19]:<20} {valor:<10} {finance[:14]:<15} {id_interno:<15}")

            print("\n")

        if invalid_entries:
            print("REGISTROS COM PROBLEMA (serão rejeitados):")
            print("-" * 80)

            # Group by error type
            error_groups = {}
            for entry in invalid_entries:
                error = entry["error"] or "Erro desconhecido"
                if error not in error_groups:
                    error_groups[error] = []
                error_groups[error].append(entry["row"])

            for error, rows in error_groups.items():
                print(f"  {error:<40} | Linhas: {', '.join(map(str, rows[:5]))}")
                if len(rows) > 5:
                    print(f"{'':40}   ... e mais {len(rows) - 5}")

            print("\n")

        # Summary statistics
        print("=" * 80)
        print("RESUMO")
        print("=" * 80)

        if valid_entries:
            print(f"\n✓ PRONTOS PARA ENVIAR: {len(valid_entries)} registros")
            print(f"\n  Ação: Executar")
            print(f"  $ python -m src.gmail_to_sheets.app run-once")
            print(f"\n  Resultado esperado:")
            print(f"  - {len(valid_entries)} transferidos para CONTAORDEM")
            print(f"  - {len(valid_entries)} FINANCE marcados como 'Transferido'")

        else:
            print(f"\n✗ NENHUM REGISTRO PRONTO")
            print(f"\n  Motivo: Todos os {len(invalid_entries)} registros têm problemas")
            print(f"  Ação: Corrigir registros inválidos em DÍZIMOS/OFERTAS")

        if invalid_entries:
            print(f"\n✗ COM PROBLEMAS: {len(invalid_entries)} registros")
            print(f"\n  Motivos mais comuns:")
            if len(invalid_entries) > 0:
                print(f"  - DOC.SOMA não está vazio")
                print(f"  - FINANCE não está vazio (já processado)")
                print(f"  - VALOR <= 0 ou vazio")
                print(f"  - DATA vazia ou inválida")

        print("\n" + "=" * 80 + "\n")

        return len(valid_entries) > 0

    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    import sys
    success = validate_sheet()
    sys.exit(0 if success else 1)
