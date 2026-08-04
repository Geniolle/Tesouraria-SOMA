"""
Attachment Processor

Handles downloading and processing MT940 attachments from Gmail.
"""

import logging
import base64
from typing import Optional

from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.parsers.mt940 import MT940Parser
from src.gmail_to_sheets.models.transaction import MT940File
from src.gmail_to_sheets.parsers.exceptions import MT940ParseError


logger = logging.getLogger(__name__)


class AttachmentProcessor:
    """Processes MT940 attachments from Gmail messages."""

    def __init__(self, gmail_client: GmailClient):
        """
        Initialize processor.

        Args:
            gmail_client: Authenticated Gmail client
        """
        self.gmail_client = gmail_client

    def process_attachment(
        self,
        message_id: str,
        attachment_id: Optional[str],
        filename: str,
    ) -> Optional[MT940File]:
        """
        Download and parse MT940 attachment.

        Args:
            message_id: Gmail message ID
            attachment_id: Gmail attachment ID (if available)
            filename: Attachment filename

        Returns:
            Parsed MT940File or None if download fails

        Raises:
            MT940ParseError: If parsing fails
        """
        try:
            logger.info(f"Processing attachment: {filename} ({message_id})")

            # Download attachment content
            content = self._download_attachment(
                message_id=message_id,
                attachment_id=attachment_id,
                filename=filename,
            )

            if not content:
                logger.warning(f"Failed to download {filename}")
                return None

            # Parse MT940 content
            parser = MT940Parser(filename=filename)
            mt940_file = parser.parse(content)

            logger.info(
                f"Successfully processed {filename}: "
                f"{mt940_file.total_transactions} transactions"
            )

            return mt940_file

        except MT940ParseError as e:
            logger.error(f"MT940 parsing error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing attachment: {e}")
            raise

    def _download_attachment(
        self,
        message_id: str,
        attachment_id: Optional[str],
        filename: str,
    ) -> Optional[str]:
        """
        Download attachment content from Gmail.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID (may be None for multipart attachments)
            filename: Attachment filename

        Returns:
            Decoded attachment content as string

        Raises:
            Exception: If download fails
        """
        try:
            if attachment_id:
                # Traditional attachment with attachmentId
                return self._download_by_attachment_id(
                    message_id, attachment_id
                )
            else:
                # Multipart attachment (inline content)
                return self._download_by_part_id(message_id, filename)

        except Exception as e:
            logger.error(f"Failed to download attachment: {e}")
            raise

    def _download_by_attachment_id(
        self,
        message_id: str,
        attachment_id: str,
    ) -> str:
        """
        Download using standard attachment ID.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID

        Returns:
            Decoded content
        """
        logger.debug(f"Downloading by attachmentId: {attachment_id}")

        attachment_data = self.gmail_client.service.users().messages().attachments().get(
            userId="me",
            messageId=message_id,
            id=attachment_id,
        ).execute()

        data = attachment_data.get("data", "")
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        logger.debug(f"Downloaded {len(decoded)} bytes")
        return decoded

    def _download_by_part_id(
        self,
        message_id: str,
        filename: str,
    ) -> str:
        """
        Download multipart attachment by filename.

        For multipart attachments, the attachmentId is in body, not part.

        Args:
            message_id: Gmail message ID
            filename: Attachment filename to match

        Returns:
            Decoded content
        """
        logger.debug(f"Downloading by filename (multipart): {filename}")

        message = self.gmail_client.get_message(message_id)
        payload = message.get("payload", {})
        parts = payload.get("parts", [])

        for part in parts:
            if part.get("filename", "").strip() == filename:
                body = part.get("body", {})
                data = body.get("data", "")

                # First try: data in body (inline)
                if data:
                    try:
                        decoded = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="replace"
                        )
                        logger.debug(f"Downloaded {len(decoded)} bytes from body.data")
                        return decoded
                    except Exception as e:
                        logger.warning(f"Error decoding body.data: {e}")

                # Second try: attachmentId in body (standard attachment)
                attachment_id = body.get("attachmentId")
                if attachment_id:
                    logger.debug(f"Using body.attachmentId: {attachment_id}")
                    try:
                        return self._download_by_attachment_id(message_id, attachment_id)
                    except Exception as e:
                        logger.warning(f"Error downloading via body.attachmentId: {e}")

                logger.error(
                    f"Attachment {filename} has no data and no attachmentId"
                )

        raise Exception(f"Attachment not found: {filename}")
