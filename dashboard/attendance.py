"""Service attendance from the AppFrequenciaMembresia sheet (same spreadsheet as
BP SERVICE). Returns only counts per service; who registered it is left out.
"""

import datetime as dt
import unicodedata
from typing import Any

from googleapiclient.discovery import build

SHEET = "AppFrequenciaMembresia"


def _key(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().strip().upper()


def _count(value: str) -> int:
    value = value.strip()
    return int(value) if value.isdigit() else 0


def fetch_attendance(credentials: Any, spreadsheet_id: str) -> list[dict[str, Any]]:
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    rows = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{SHEET}'")
        .execute()
        .get("values", [])
    )
    if not rows:
        return []
    col = {_key(h): i for i, h in enumerate(rows[0])}

    def cell(r: list[str], name: str) -> str:
        i = col.get(name)
        return r[i] if i is not None and i < len(r) else ""

    out = []
    for r in rows[1:]:
        try:
            day = dt.datetime.strptime(cell(r, "DATA").strip(), "%d/%m/%Y").date()
        except ValueError:
            continue
        out.append(
            {
                "date": day.isoformat(),
                "tipo": cell(r, "TIPO").strip().upper(),
                "mem": _count(cell(r, "MEMBRESIA")),
                "vis": _count(cell(r, "VISITANTES")),
                "cri": _count(cell(r, "CRIANCAS")),
            }
        )
    return out
