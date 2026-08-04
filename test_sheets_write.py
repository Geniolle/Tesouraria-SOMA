#!/usr/bin/env python3
"""
Google Sheets Write Test

Tests the complete pipeline:
1. Search Gmail for MT940 attachment
2. Download and parse
3. Load existing transactions
4. Write new ones to Google Sheets

Usage:
    python test_sheets_write.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.services.sheets_writer import SheetsWriter
from src.gmail_to_sheets.validators.deduplication import DeduplicationService


def main() -> None:
    """Run sheets write test."""
    load_dotenv()
    setup_logging("logs/test-sheets-write.log", "INFO")

    try:
        print("\n" + "=" * 80)
        print("TESTE DE ESCRITA NO GOOGLE SHEETS")
        print("=" * 80 + "\n")

        # Load configuration
        print("1. Loading configuration...")
        settings = load_settings()
        print(f"   Gmail: {settings.gmail.account_email}")
        print(f"   Sheets: {settings.sheets.spreadsheet_id}\n")

        # Authenticate Gmail
        print("2. Authenticating with Gmail...")
        gmail_auth = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        gmail_creds = gmail_auth.get_credentials()
        gmail_client = GmailClient(gmail_creds)
        print("   [OK] Gmail authenticated\n")

        # Authenticate Sheets
        print("3. Authenticating with Google Sheets...")
        sheets_client = SheetsClient(
            service_account_path=settings.sheets.service_account_path
        )
        print("   [OK] Sheets authenticated\n")

        # Initialize writer
        print("4. Initializing Sheets writer...")
        sheets_writer = SheetsWriter(
            sheets_client=sheets_client,
            spreadsheet_id=settings.sheets.spreadsheet_id,
            sheet_name=settings.sheets.sheet_name,
        )
        print(f"   [OK] Found {len(sheets_writer.headers)} columns\n")

        # Load existing transactions
        print("5. Loading existing transactions for deduplication...")
        dedup = DeduplicationService()
        sheets_writer.load_existing_dedup_keys(dedup)
        stats = dedup.get_stats()
        print(f"   [OK] Loaded {stats['total_seen']} existing transactions\n")

        # Search Gmail
        print("6. Searching Gmail for MT940 attachments...")
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=1,
        )

        if not message_ids:
            print("   [ERROR] No emails found!")
            return

        print(f"   [OK] Found {len(message_ids)} email(s)\n")

        # Download and parse
        print("7. Downloading and parsing MT940...")
        message_id = message_ids[0]
        attachments = gmail_client.get_attachments(message_id)

        if not attachments:
            print("   [ERROR] No attachments found!")
            return

        processor = AttachmentProcessor(gmail_client)
        mt940_file = processor.process_attachment(
            message_id=message_id,
            attachment_id=attachments[0].get("attachment_id"),
            filename=attachments[0]["filename"],
        )

        print(f"   [OK] Parsed {mt940_file.total_transactions} transactions\n")

        # Write to Sheets
        print("8. Writing transactions to Google Sheets...")
        print(f"   Sheet: {settings.sheets.sheet_name}")
        print(f"   Spreadsheet ID: {settings.sheets.spreadsheet_id[:20]}...\n")

        result = sheets_writer.write_transactions(
            transactions=mt940_file.transactions,
            dedup_service=dedup,
        )

        print(f"   [OK] Write completed!")
        print(f"       - Written: {result['written']}")
        print(f"       - Skipped (duplicates): {result['skipped']}")
        print(f"       - Total processed: {result['total']}\n")

        # Summary
        print("=" * 80)
        print("RESUMO")
        print("=" * 80)
        print(f"\nEmail processado: {attachments[0]['filename']}")
        print(f"Transacoes parseadas: {mt940_file.total_transactions}")
        print(f"Transacoes escritas: {result['written']}")
        print(f"Saldo inicial: {mt940_file.header.saldo_abertura} EUR")
        print(f"Saldo final: {mt940_file.footer.saldo_fecho} EUR")
        print(f"\nSheet URL: https://docs.google.com/spreadsheets/d/{settings.sheets.spreadsheet_id}")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
