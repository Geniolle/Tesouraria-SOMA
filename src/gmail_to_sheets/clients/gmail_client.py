"""
Gmail API client for message and attachment operations.

Handles searching, retrieving, and processing Gmail messages.
"""

import base64
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GmailClient:
    """Client for Gmail API operations."""

    def __init__(self, credentials: Credentials) -> None:
        """
        Initialize Gmail client.

        Args:
            credentials: OAuth2 credentials for Gmail API
        """
        self.credentials = credentials
        self.service = build("gmail", "v1", credentials=credentials)

    def search_messages(self, query: str, max_results: int = 100) -> list[str]:
        """
        Search for messages matching query.

        Args:
            query: Gmail search query (e.g., 'from:sender@example.com has:attachment')
            max_results: Maximum number of message IDs to return

        Returns:
            List of message IDs matching the query

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            logger.debug(f"Searching Gmail with query: {query}")
            results = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            message_ids = [msg["id"] for msg in messages]
            logger.info(f"Found {len(message_ids)} messages matching query")

            return message_ids
        except HttpError as error:
            logger.error(f"Gmail API error during search: {error}")
            raise

    def get_message(self, message_id: str, format_type: str = "full") -> dict[str, Any]:
        """
        Retrieve full message details.

        Args:
            message_id: The ID of the message to retrieve
            format_type: "full", "minimal", or "raw"

        Returns:
            Message object with headers, body, attachments

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            message = self.service.users().messages().get(
                userId="me", id=message_id, format=format_type
            ).execute()
            return message
        except HttpError as error:
            logger.error(f"Failed to retrieve message {message_id}: {error}")
            raise

    def get_attachments(
        self, message_id: str, attachment_extension: str = ".txt"
    ) -> list[dict[str, Any]]:
        """
        Get all attachments from a message.

        Args:
            message_id: The ID of the message
            attachment_extension: Filter attachments by extension (e.g., '.txt')

        Returns:
            List of attachment objects with name and MIME type

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            message = self.get_message(message_id)
            payload = message.get("payload", {})
            parts = payload.get("parts", [])

            attachments = []
            for part in parts:
                filename = part.get("filename", "").strip()
                if filename and filename.lower().endswith(attachment_extension.lower()):
                    attachment_id = part.get("attachmentId")
                    attachments.append(
                        {
                            "filename": filename,
                            "attachment_id": attachment_id,
                            "mime_type": part.get("mimeType", ""),
                            "part_id": part.get("partId"),
                        }
                    )

            logger.debug(
                f"Found {len(attachments)} attachments in message {message_id}"
            )
            return attachments
        except HttpError as error:
            logger.error(f"Failed to get attachments from {message_id}: {error}")
            raise

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """
        Download attachment data.

        Args:
            message_id: The ID of the message containing the attachment
            attachment_id: The ID of the attachment

        Returns:
            Raw bytes of the attachment

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            attachment = self.service.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute()

            data = attachment.get("data", "")
            file_data = base64.urlsafe_b64decode(data)
            logger.debug(f"Downloaded attachment {attachment_id}")

            return file_data
        except HttpError as error:
            logger.error(
                f"Failed to download attachment {attachment_id}: {error}"
            )
            raise

    def get_or_create_label_id(self, label_name: str) -> str:
        """
        Get label ID, with Unicode-safe lookup and creation fallback.

        Handles label normalization (NFC), case-folding, and hierarchical paths.
        Tolerates HTTP 409 Conflict during creation by retrying lookup.

        Args:
            label_name: The label name (e.g., 'Serviços/Banco/Montepio24/MT940')

        Returns:
            Label ID string

        Raises:
            HttpError: If label lookup/creation fails
        """
        import unicodedata

        # Normalize label name for comparison
        normalized_target = unicodedata.normalize("NFC", label_name.strip())

        try:
            labels_result = self.service.users().labels().list(userId="me").execute()
            labels = labels_result.get("labels", [])

            # Search for exact match with Unicode normalization
            for label in labels:
                label_name_normalized = unicodedata.normalize("NFC", label["name"].strip())
                if label_name_normalized == normalized_target:
                    logger.debug(f"Found existing label: {label['name']} -> {label['id']}")
                    return label["id"]

            # Not found, try to create it
            logger.info(f"Label '{label_name}' not found, attempting to create")
            label_body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }

            try:
                created_label = self.service.users().labels().create(
                    userId="me", body=label_body
                ).execute()
                label_id = created_label["id"]
                logger.info(f"Created new label: {label_name} -> {label_id}")
                return label_id

            except HttpError as creation_error:
                # HTTP 409 Conflict means label exists but wasn't found above
                # This can happen with Unicode variations, so retry lookup
                if creation_error.resp.status == 409:
                    logger.info("Label creation got 409 (already exists), retrying lookup")
                    labels_result = self.service.users().labels().list(userId="me").execute()
                    labels = labels_result.get("labels", [])

                    for label in labels:
                        label_name_normalized = unicodedata.normalize("NFC", label["name"].strip())
                        if label_name_normalized == normalized_target:
                            logger.info(f"Found after 409: {label['name']} -> {label['id']}")
                            return label["id"]

                    # Still not found? Raise the original error
                    logger.error(f"Label not found after 409 conflict: {label_name}")
                    raise

                # Other HTTP error
                logger.error(f"Failed to create label '{label_name}': {creation_error}")
                raise

        except HttpError as error:
            if error.resp.status == 409:
                logger.info("Label creation/lookup got 409, treating as exists")
                raise
            logger.error(f"Failed to get or create label: {error}")
            raise

    def add_label(self, message_id: str, label_name: str) -> None:
        """
        Add a label to a message.

        Args:
            message_id: The ID of the message
            label_name: The label name (e.g., 'Serviços/Banco/Montepio24/MT940')

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            label_id = self.get_or_create_label_id(label_name)

            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()

            logger.debug(f"Added label '{label_name}' (ID: {label_id}) to message {message_id}")
        except HttpError as error:
            logger.error(f"Failed to add label to message {message_id}: {error}")
            raise

    def archive_message(self, message_id: str) -> None:
        """
        Archive a message (remove from inbox).

        Args:
            message_id: The ID of the message

        Raises:
            HttpError: If Gmail API call fails
        """
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["INBOX"]},
            ).execute()

            logger.debug(f"Archived message {message_id}")
        except HttpError as error:
            logger.error(f"Failed to archive message {message_id}: {error}")
            raise
