"""File names in the accountant's Drive folders (receipts and fixed-cost invoices).

The page compares them with the DÍZIMOS/OFERTAS and SAÍDAS rows of the month
to show what has been delivered to the accountant. Only names leave the
server, never file contents.
"""

import json
import re
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


def parse_expected(text: str) -> list[dict[str, Any]]:
    """Expected monthly invoices: JSON list of {nome, padrao, qtd, desde?}.

    `padrao` is a regex matched (case-insensitive) against the file name after
    its date, `qtd` the invoices expected per month, `desde` the first month
    (yyyy-MM) the supplier applies. Raises ValueError on a malformed entry.
    """
    if not text.strip():
        return []
    items = json.loads(text)
    if not isinstance(items, list):
        raise ValueError("expected a JSON list")
    out = []
    for item in items:
        nome, padrao, qtd = item.get("nome"), item.get("padrao"), item.get("qtd", 1)
        desde = item.get("desde", "")
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("nome em falta")
        if not isinstance(padrao, str) or not padrao:
            raise ValueError(f"{nome}: padrao em falta")
        re.compile(padrao)
        if not isinstance(qtd, int) or isinstance(qtd, bool) or qtd < 1:
            raise ValueError(f"{nome}: qtd inválida")
        if desde and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", desde):
            raise ValueError(f"{nome}: desde inválido")
        out.append({"nome": nome.strip(), "padrao": padrao, "qtd": qtd, "desde": desde})
    return out


def from_year(names: list[str], min_year: str | None) -> list[str]:
    """Keep names whose leading date (yyyyMMdd_ or yyyy_MM_dd_) is in min_year or later."""
    if not min_year:
        return names
    return [n for n in names if n[:4].isdigit() and n[:4] >= min_year]
