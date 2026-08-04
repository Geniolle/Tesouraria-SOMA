#!/usr/bin/env python3
"""
Gmail Message Debug

Shows the raw structure of the email to diagnose attachment issues.
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
    """Debug email structure."""
    load_dotenv()
    setup_logging("logs/test-gmail-debug.log", "INFO")

    try:
        print("\nGmail Message Debug\n")

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
        message = gmail_client.get_message(message_id)

        print(f"Message ID: {message_id}\n")
        print("Payload structure:")
        print("-" * 70)

        payload = message.get("payload", {})
        print(f"- mimeType: {payload.get('mimeType')}")
        print(f"- headers: {len(payload.get('headers', []))} items")
        print(f"- parts: {len(payload.get('parts', []))} items")
        print(f"- body: {len(payload.get('body', {}).get('data', ''))} bytes\n")

        parts = payload.get("parts", [])
        if parts:
            print(f"Parts ({len(parts)}):")
            for idx, part in enumerate(parts):
                print(f"\n  Part {idx + 1}:")
                print(f"    mimeType: {part.get('mimeType')}")
                print(f"    filename: {part.get('filename', '(no filename)')}")
                print(f"    partId: {part.get('partId')}")
                print(f"    headers: {len(part.get('headers', []))} items")
                if "attachmentId" in part:
                    print(f"    attachmentId: {part['attachmentId']}")
                body = part.get("body", {})
                print(f"    body.size: {body.get('size', 0)} bytes")
        else:
            print("No parts found in payload")
            body = payload.get("body", {})
            print(f"Body: {len(body.get('data', ''))} bytes")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
