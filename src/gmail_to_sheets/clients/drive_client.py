"""Google Drive API client for uploading files into a folder.

Uses the same OAuth credentials as :class:`GmailClient` (the ``drive.file``
scope, which only grants access to files this app creates). Intended for the
Faturas Email process, which saves email attachments to a Drive folder.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)


class DriveClient:
    """Minimal Google Drive v3 client scoped to folder uploads."""

    def __init__(self, credentials: Credentials) -> None:
        self.credentials = credentials
        self.service = build("drive", "v3", credentials=credentials)

    def list_child_names(self, folder_id: str) -> set[str]:
        """Return the names of the non-trashed files this app put in a folder.

        With the ``drive.file`` scope this only lists files the app itself
        created (which is exactly what duplicate detection needs); files a
        person added by hand are invisible and never clash.
        """
        names: set[str] = set()
        page_token: str | None = None
        try:
            while True:
                resp = self.service.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(name)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
                for item in resp.get("files", []):
                    name = item.get("name")
                    if name:
                        names.add(name)
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as error:
            logger.error(
                "Failed to list Drive folder %s: %s", folder_id, error
            )
            raise
        return names

    def upload_bytes(
        self,
        name: str,
        data: bytes,
        mime_type: str,
        folder_id: str,
    ) -> dict[str, Any]:
        """Create a new file with ``data`` inside ``folder_id``."""
        media = MediaIoBaseUpload(
            io.BytesIO(data),
            mimetype=mime_type or "application/octet-stream",
            resumable=False,
        )
        try:
            created = self.service.files().create(
                body={"name": name, "parents": [folder_id]},
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            ).execute()
            logger.info(
                "Uploaded %r to Drive folder %s (id=%s)",
                created.get("name"),
                folder_id,
                created.get("id"),
            )
            return created
        except HttpError as error:
            logger.error(
                "Failed to upload %r to Drive folder %s: %s",
                name,
                folder_id,
                error,
            )
            raise
