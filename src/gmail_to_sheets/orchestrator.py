"""
Orchestrator: Coordinates the Gmail-to-Sheets pipeline.

Responsibilities:
- Load configuration
- Authenticate with Gmail and Google Sheets
- Manage the flow from discovery to writing
- Handle errors and logging
"""

import logging
from pathlib import Path

from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.exceptions.application import ConfigurationError, AuthenticationError


logger = logging.getLogger(__name__)


class Orchestrator:
    """Main flow controller for the gmail-to-sheets pipeline."""

    def __init__(self) -> None:
        """Initialize the orchestrator."""
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.gmail_client: GmailClient | None = None

    def run(self) -> None:
        """Execute the complete pipeline."""
        try:
            logger.info("Starting gmail-to-sheets pipeline")

            # Phase 1: Load configuration
            logger.info(f"Configuration loaded: account={self.settings.gmail.account_email}")

            # Phase 2: Authenticate
            self._authenticate_gmail()

            # Phase 3: Search Gmail
            self._search_messages()

            # Phase 4-7: Deferred to next phases

            logger.info("Pipeline completed successfully")
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise

    def _authenticate_gmail(self) -> None:
        """Authenticate with Gmail API."""
        try:
            logger.info("Authenticating with Gmail API...")
            authenticator = GmailAuthenticator(
                client_secrets_path=self.settings.gmail.client_secrets_path,
                credentials_path=self.settings.gmail.credentials_path,
            )
            credentials = authenticator.get_credentials()
            self.gmail_client = GmailClient(credentials)
            logger.info("Gmail authentication successful")
        except Exception as e:
            logger.error(f"Gmail authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with Gmail: {e}") from e

    def _search_messages(self) -> None:
        """Search for messages matching criteria."""
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")

        try:
            logger.info(f"Searching for messages: {self.settings.gmail.search_query}")
            message_ids = self.gmail_client.search_messages(
                query=self.settings.gmail.search_query,
                max_results=self.settings.batch_size,
            )
            logger.info(f"Found {len(message_ids)} messages")
        except Exception as e:
            logger.error(f"Message search failed: {e}")
            raise
