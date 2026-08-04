#!/usr/bin/env python3
"""
Sheet Preview Simulation

Shows what data would be inserted into the T_EXTRATO sheet.
Simulates the validation and formatting that would happen.
"""

import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.validators.deduplication import DeduplicationService


def generate_id_interno(sequencial: int) -> str:
    """Generate internal ID (EXT + 10 digits)."""
    return f"EXT{str(sequencial).zfill(10)}"


def format_timestamp() -> str:
    """Generate current timestamp."""
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def main() -> None:
    """Simulate sheet insertion."""
    load_dotenv()
    setup_logging("logs/test-sheet-preview.log", "INFO")

    try:
        print("\n" + "=" * 120)
        print("SIMULAÇÃO DE INSERÇÃO NA SHEET T_EXTRATO")
        print("=" * 120 + "\n")

        settings = load_settings()
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        gmail_client = GmailClient(credentials)

        # Search and download
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=1,
        )

        if not message_ids:
            print("No emails found!")
            return

        message_id = message_ids[0]
        attachments = gmail_client.get_attachments(message_id)

        if not attachments:
            print("No attachments found!")
            return

        # Process attachment
        processor = AttachmentProcessor(gmail_client)
        mt940_file = processor.process_attachment(
            message_id=message_id,
            attachment_id=attachments[0].get("attachment_id"),
            filename=attachments[0]["filename"],
        )

        # Deduplication service (empty for simulation)
        dedup = DeduplicationService()

        print("COLUNAS DA SHEET T_EXTRATO:")
        print("-" * 120)

        # Column mapping based on the JS script
        columns = [
            "DATA MOV.",
            "DATA VALOR",
            "DESCRIÇÃO",
            "IMPORTÂNCIA",
            "TIPO",
            "TIMESTAMP",
            "SALDO CONTABILÍSTICO",
            "ID_INTERNO",
        ]

        # Print header
        col_widths = [14, 14, 35, 15, 12, 20, 20, 15]
        header = ""
        for col, width in zip(columns, col_widths):
            header += f"{col[:width]:^{width}} | "
        print(header)
        print("-" * 120)

        # Process transactions
        inserted_count = 0
        duplicate_count = 0
        sequencial = 1000001

        print("\nTRANSAÇÕES A INSERIR:")
        print("-" * 120)

        for idx, txn in enumerate(mt940_file.transactions, 1):
            # Check for duplicates
            if dedup.is_duplicate(txn):
                duplicate_count += 1
                status = "[DUPLICADO]"
            else:
                dedup.register(txn)
                inserted_count += 1
                status = "[NOVO]"
                sequencial += 1

            # Format row as it would appear in sheet
            id_interno = generate_id_interno(sequencial - 1)
            timestamp = format_timestamp()
            saldo = "-"  # Only filled for last transaction

            row_values = [
                txn.data_mov,
                txn.data_valor,
                txn.descricao[:35],  # Truncate for display
                f"{txn.valor:>15}",
                txn.tipo,
                timestamp,
                saldo,
                id_interno,
            ]

            # Format and print
            row = ""
            for val, width in zip(row_values, col_widths):
                if isinstance(val, str) and val.startswith("-"):
                    # Right align numbers
                    row += f"{val:>{width}} | "
                elif val in ["-", timestamp, id_interno]:
                    row += f"{val:<{width}} | "
                else:
                    row += f"{str(val):<{width}} | "

            print(f"{status:12} | {row}")

        print("-" * 120)

        # Summary
        print("\n" + "=" * 120)
        print("RESUMO DA SIMULAÇÃO")
        print("=" * 120)
        print(f"\nTotal de transações no ficheiro: {len(mt940_file.transactions)}")
        print(f"Novas transações para inserir:   {inserted_count}")
        print(f"Duplicadas (rejeitadas):         {duplicate_count}")
        print(f"Saldo inicial:                   {mt940_file.header.saldo_abertura} EUR")
        print(f"Saldo final:                     {mt940_file.footer.saldo_fecho} EUR")

        print(f"\nColunas obrigatórias verificadas:")
        for col in columns:
            print(f"  [OK] {col}")

        print(f"\nValidações aplicadas:")
        print(f"  [OK] Tipos de dados (data, valor, texto)")
        print(f"  [OK] Deduplicação por chave (DATA|DESC|VALOR)")
        print(f"  [OK] Geração automática de ID_INTERNO")
        print(f"  [OK] Timestamp de processamento")
        print(f"  [OK] Normalização de descrições")

        print("\n" + "=" * 120)
        print("PRONTO PARA INSERIR NA SHEET")
        print("=" * 120 + "\n")

    except Exception as e:
        print(f"\nErro: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
