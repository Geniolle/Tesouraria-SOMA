#!/usr/bin/env python3
"""
OAuth Test Script

This script tests Gmail OAuth authentication and validates the connection.

On first run:
1. Opens your browser for Gmail login
2. Saves the token to credentials/gmail-oauth-token.json
3. Tests the Gmail API connection

Usage:
    python test_oauth.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging


def main() -> None:
    """Run OAuth test."""
    # Load environment
    load_dotenv()

    # Setup logging
    setup_logging("logs/test-oauth.log", "DEBUG")
    logger = logging.getLogger(__name__)

    try:
        logger.info("=" * 60)
        logger.info("Gmail OAuth Test")
        logger.info("=" * 60)

        # Load configuration
        logger.info("\n1. Loading configuration...")
        settings = load_settings()
        logger.info(f"   Email: {settings.gmail.account_email}")
        logger.info(f"   Client secrets: {settings.gmail.client_secrets_path}")
        logger.info(f"   Token cache: {settings.gmail.credentials_path}")

        # Authenticate
        logger.info("\n2. Authenticating with Gmail...")
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        logger.info("   ✓ Authentication successful!")

        # Create client
        logger.info("\n3. Creating Gmail client...")
        gmail_client = GmailClient(credentials)
        logger.info("   ✓ Client created!")

        # Test search
        logger.info("\n4. Testing search query...")
        logger.info(f"   Query: {settings.gmail.search_query}")
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=5,
        )
        logger.info(f"   ✓ Found {len(message_ids)} messages")

        if message_ids:
            logger.info("\n5. Sample message details...")
            sample_id = message_ids[0]
            message = gmail_client.get_message(sample_id)
            headers = message.get("payload", {}).get("headers", [])
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"),
                "(no subject)",
            )
            from_addr = next(
                (h["value"] for h in headers if h["name"] == "From"),
                "(unknown)",
            )
            logger.info(f"   From: {from_addr}")
            logger.info(f"   Subject: {subject}")

            attachments = gmail_client.get_attachments(
                sample_id,
                attachment_extension=settings.attachment_extension,
            )
            logger.info(f"   Attachments: {len(attachments)}")
            for att in attachments:
                logger.info(f"     - {att['filename']}")

        logger.info("\n" + "=" * 60)
        logger.info("✓ All tests passed!")
        logger.info("=" * 60)
        logger.info("\nOAuth token saved to:")
        logger.info(f"  {settings.gmail.credentials_path}")
        logger.info("\nYou can now use the application:")
        logger.info("  python -m src.gmail_to_sheets")

    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
