#!/usr/bin/env python3
"""
MT940 Parsing Test

Tests MT940 parsing pipeline:
1. Search for email with MT940 attachment
2. Download attachment directly
3. Parse MT940 content
4. Validate transactions

Usage:
    python test_mt940_parsing.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.validators.deduplication import DeduplicationService


def main() -> None:
    """Run MT940 parsing test."""
    load_dotenv()
    setup_logging("logs/test-mt940-parsing.log", "INFO")

    try:
        print("\n" + "=" * 70)
        print("MT940 Parsing Pipeline Test")
        print("=" * 70 + "\n")

        # Load configuration
        print("1. Loading configuration...")
        settings = load_settings()
        print(f"   Account: {settings.gmail.account_email}\n")

        # Authenticate
        print("2. Authenticating with Gmail...")
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        gmail_client = GmailClient(credentials)
        print("   [OK] Authentication successful\n")

        # Search
        print("3. Searching for emails with MT940 attachments...")
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=5,
        )

        if not message_ids:
            print("   [ERROR] No emails found!\n")
            return

        print(f"   [OK] Found {len(message_ids)} email(s)\n")

        # Initialize processor and deduplication
        processor = AttachmentProcessor(gmail_client)
        dedup = DeduplicationService()

        # Process first email
        message_id = message_ids[0]
        message = gmail_client.get_message(message_id)
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        subject = next(
            (h["value"] for h in headers if h["name"] == "Subject"),
            "(no subject)",
        )
        date_str = next(
            (h["value"] for h in headers if h["name"] == "Date"),
            "(unknown)",
        )

        print(f"4. Processing first email:")
        print(f"   Subject: {subject}")
        print(f"   Date: {date_str}\n")

        # Get attachments
        attachments = gmail_client.get_attachments(
            message_id,
            attachment_extension=settings.attachment_extension,
        )

        if not attachments:
            print("   [ERROR] No .txt attachments found!\n")
            return

        print(f"   [OK] Found {len(attachments)} attachment(s)\n")

        # Download and parse each attachment
        print("5. Parsing MT940 attachments:\n")
        print("-" * 70)

        total_transactions = 0

        for att in attachments:
            print(f"\nAttachment: {att['filename']}")
            print(f"  Type: {att['mime_type']}")

            try:
                # Process attachment
                mt940_file = processor.process_attachment(
                    message_id=message_id,
                    attachment_id=att.get("attachment_id"),
                    filename=att["filename"],
                )

                if not mt940_file:
                    print("  [ERROR] Failed to process attachment")
                    continue

                print(f"  [OK] Parsed successfully")
                print(f"      Opening balance: {mt940_file.header.saldo_abertura}")
                print(f"      Closing balance: {mt940_file.footer.saldo_fecho}")
                print(f"      Transactions: {mt940_file.total_transactions}")

                total_transactions += mt940_file.total_transactions

                # Show first few transactions
                if mt940_file.transactions:
                    print(f"\n      First 3 transactions:")
                    for i, txn in enumerate(
                        mt940_file.transactions[:3], 1
                    ):
                        print(
                            f"        {i}. [{txn.data_mov}] "
                            f"{txn.descricao[:40]:40} "
                            f"{txn.valor:>12} ({txn.tipo})"
                        )

                    if len(mt940_file.transactions) > 3:
                        remaining = len(mt940_file.transactions) - 3
                        print(f"      ... and {remaining} more transactions")

            except Exception as e:
                print(f"  [ERROR] Failed to parse: {e}")
                continue

        print("\n" + "=" * 70)
        print(f"[OK] Test completed!")
        print(f"Total transactions parsed: {total_transactions}")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
