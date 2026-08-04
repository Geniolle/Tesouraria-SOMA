#!/usr/bin/env python3
"""
MT940 Content Debug

Shows the raw content of the MT940 attachment.
"""

import sys
from pathlib import Path
import base64

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor


def main() -> None:
    """Show MT940 content."""
    load_dotenv()
    setup_logging("logs/test-mt940-content.log", "INFO")

    try:
        settings = load_settings()
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        gmail_client = GmailClient(credentials)

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

        processor = AttachmentProcessor(gmail_client)

        for att in attachments:
            print(f"\nAttachment: {att['filename']}\n")
            print("=" * 70)

            content = processor._download_attachment(
                message_id=message_id,
                attachment_id=att.get("attachment_id"),
                filename=att["filename"],
            )

            print("Content (first 3000 chars):")
            print("-" * 70)
            print(content[:3000])
            print("-" * 70)
            print(f"\nTotal length: {len(content)} chars")
            print(f"Total lines: {len(content.split(chr(10)))}")

            # Show lines with tags
            print("\nLines with MT940 tags:")
            for idx, line in enumerate(content.split("\n"), 1):
                if line.startswith(":"):
                    print(f"  Line {idx}: {line[:80]}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
