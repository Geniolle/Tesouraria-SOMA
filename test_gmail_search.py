#!/usr/bin/env python3
"""
Gmail Search Test

Tests Gmail search for MT940 emails from Montepio.
Shows email details: subject, sender, date, attachments.

Usage:
    python test_gmail_search.py
"""

import sys
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging


def format_email_date(date_str: str) -> str:
    """Convert email date to readable format."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return date_str


def main() -> None:
    """Run Gmail search test."""
    load_dotenv()
    setup_logging("logs/test-gmail-search.log", "INFO")

    try:
        print("\n" + "=" * 70)
        print("Gmail Search Test: Finding MT940 Emails")
        print("=" * 70 + "\n")

        # Load configuration
        print("1. Loading configuration...")
        settings = load_settings()
        print(f"   Account: {settings.gmail.account_email}")
        print(f"   Query: {settings.gmail.search_query}\n")

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
        print("3. Searching for emails...")
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=10,
        )

        if not message_ids:
            print("   [ERROR] No emails found!\n")
            return

        print(f"   [OK] Found {len(message_ids)} email(s)\n")

        # Process each email
        print("4. Email Details:")
        print("-" * 70)

        for idx, message_id in enumerate(message_ids, 1):
            message = gmail_client.get_message(message_id)
            payload = message.get("payload", {})
            headers = payload.get("headers", [])

            # Extract headers
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"),
                "(no subject)",
            )
            from_addr = next(
                (h["value"] for h in headers if h["name"] == "From"),
                "(unknown)",
            )
            date_str = next(
                (h["value"] for h in headers if h["name"] == "Date"),
                "(unknown)",
            )

            formatted_date = format_email_date(date_str)

            print(f"\nEmail #{idx}")
            print(f"  ID: {message_id}")
            print(f"  From: {from_addr}")
            print(f"  Subject: {subject}")
            print(f"  Date: {formatted_date}")

            # Get attachments with filter
            attachments = gmail_client.get_attachments(
                message_id,
                attachment_extension=settings.attachment_extension,
            )

            # Get ALL attachments (any extension) for debugging
            payload = message.get("payload", {})
            parts = payload.get("parts", [])
            all_attachments = []
            for part in parts:
                if part.get("filename") and "attachmentId" in part:
                    all_attachments.append({
                        "filename": part.get("filename", ""),
                        "mimeType": part.get("mimeType", ""),
                    })

            if attachments:
                print(f"  Attachments (.txt): {len(attachments)} file(s)")
                for att in attachments:
                    print(f"    - {att['filename']}")
            else:
                print(f"  Attachments (.txt): None")

            if all_attachments and not attachments:
                print(f"  All attachments in message: {len(all_attachments)} file(s)")
                for att in all_attachments:
                    print(f"    - {att['filename']} ({att['mimeType']})")

        print("\n" + "=" * 70)
        print("[OK] Test completed successfully!")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n✗ Test failed: {e}\n", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
