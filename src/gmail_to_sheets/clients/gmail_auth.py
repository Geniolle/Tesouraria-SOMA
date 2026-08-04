"""
Gmail OAuth 2.0 authentication and service initialization.

Handles the OAuth flow, token storage, and Gmail service creation.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


logger = logging.getLogger(__name__)


class GmailAuthenticator:
    """Manages Gmail OAuth authentication."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

    def __init__(self, client_secrets_path: Path, credentials_path: Path) -> None:
        """
        Initialize authenticator.

        Args:
            client_secrets_path: Path to oauth2 client secrets JSON from Google Cloud Console
            credentials_path: Path where OAuth tokens will be stored
        """
        self.client_secrets_path = Path(client_secrets_path)
        self.credentials_path = Path(credentials_path)

        if not self.client_secrets_path.exists():
            raise FileNotFoundError(
                f"Client secrets not found at {self.client_secrets_path}\n"
                f"Download it from Google Cloud Console and place it there."
            )

    def get_credentials(self) -> Credentials:
        """
        Get valid credentials for Gmail API.

        Returns cached token if available and valid, otherwise initiates OAuth flow.

        Returns:
            google.oauth2.credentials.Credentials: Valid credentials

        Raises:
            FileNotFoundError: If client secrets file not found
        """
        credentials: Optional[Credentials] = None

        if self.credentials_path.exists():
            logger.info(f"Loading cached credentials from {self.credentials_path}")
            credentials = Credentials.from_authorized_user_file(
                str(self.credentials_path), self.SCOPES
            )

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                logger.info("Refreshing expired credentials")
                credentials.refresh(Request())
            else:
                logger.info("Initiating new OAuth flow")
                credentials = self._get_new_credentials()

            self._save_credentials(credentials)

        return credentials

    def _get_new_credentials(self) -> Credentials:
        """
        Initiate OAuth 2.0 authorization flow.

        Opens browser for user to authorize access.

        Returns:
            google.oauth2.credentials.Credentials: Authorized credentials
        """
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_path), self.SCOPES
        )

        credentials = flow.run_local_server(port=0)
        logger.info("OAuth authorization successful")
        return credentials

    def _save_credentials(self, credentials: Credentials) -> None:
        """
        Save credentials to file for future use.

        Args:
            credentials: The credentials to save
        """
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.credentials_path, "w") as token_file:
            token_file.write(credentials.to_json())

        logger.info(f"Credentials saved to {self.credentials_path}")
