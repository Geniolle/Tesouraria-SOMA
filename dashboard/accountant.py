"""File names in the accountant's Drive folders (receipts and fixed-cost invoices).

The page compares them with the DÍZIMOS/OFERTAS and SAÍDAS rows of the month
to show what has been delivered to the accountant. Only names leave the
server, never file contents.
"""

from typing import Any

from googleapiclient.discovery import build

FOLDER_MIME = "application/vnd.google-apps.folder"


def list_names(creds: Any, folder_id: str) -> list[str]:
    """Names of the files directly inside a Drive folder (sub-folders skipped)."""
    files = build("drive", "v3", credentials=creds, cache_discovery=False).files()
    names: list[str] = []
    token = None
    while True:
        page = files.list(
            q=f"'{folder_id}' in parents and trashed = false and mimeType != '{FOLDER_MIME}'",
            fields="nextPageToken, files(name)",
            pageSize=1000,
            pageToken=token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        names += [f["name"] for f in page.get("files", [])]
        token = page.get("nextPageToken")
        if not token:
            return names


def from_year(names: list[str], min_year: str | None) -> list[str]:
    """Keep names whose leading date (yyyyMMdd_ or yyyy_MM_dd_) is in min_year or later."""
    if not min_year:
        return names
    return [n for n in names if n[:4].isdigit() and n[:4] >= min_year]
