#!/usr/bin/env python3
"""
Debug: Attachment Structure

Inspects the exact structure of the MT940 attachment from Gmail.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging


def main() -> None:
    """Debug attachment structure."""
    load_dotenv()
    setup_logging("logs/test-attachment-structure.log", "INFO")

    try:
        print("\nDebug: Attachment Structure\n")

        settings = load_settings()
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        gmail_client = GmailClient(credentials)

        # Search
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=1,
        )

        if not message_ids:
            print("No emails found!")
            return

        message_id = message_ids[0]
        message = gmail_client.get_message(message_id, format_type="full")

        payload = message.get("payload", {})
        parts = payload.get("parts", [])

        print(f"Message has {len(parts)} parts\n")

        for idx, part in enumerate(parts):
            print(f"Part {idx}:")
            print(f"  mimeType: {part.get('mimeType')}")
            print(f"  filename: {part.get('filename', '(none)')}")
            print(f"  partId: {part.get('partId', '(none)')}")
            print(f"  headers: {len(part.get('headers', []))} items")

            body = part.get("body", {})
            print(f"  body keys: {list(body.keys())}")
            print(f"  body.size: {body.get('size', 0)}")
            print(f"  body.data: {len(body.get('data', ''))} chars")

            if body.get("data"):
                print(f"  body.data (first 100 chars): {body['data'][:100]}")

            print()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
