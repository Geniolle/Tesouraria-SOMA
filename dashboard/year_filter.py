"""Drop rows dated before a given year from an XLSX export.

Used so non-admin members never receive older years. Each sheet's date column
is found by header; sheets without one (e.g. CONSTANTES) are copied as they
are, and rows without a readable date are kept. Number formats are preserved
so the page parses dates and amounts exactly as from the original export.
"""

import datetime as dt
import io
import unicodedata

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell

DATE_HEADERS = ("DATA MOV.", "DATA MOV", "DATA")


def _key(text: object) -> str:
    plain = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode()
    return plain.strip().upper()


def _flat(text: str) -> str:
    return "".join(ch for ch in _key(text) if ch.isalnum())


def _year(value: object) -> int | None:
    if isinstance(value, dt.date):
        return value.year
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text[:10], fmt).year
        except ValueError:
            pass
    return None


def filter_xlsx(data: bytes, min_year: int, sheets: set[str] | None = None) -> bytes:
    """sheets: titles to keep (compared without accents/punctuation); None keeps all."""
    keep = {_flat(s) for s in sheets} if sheets else None
    src = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = Workbook(write_only=True)
    for ws in src.worksheets:
        if keep is not None and _flat(ws.title) not in keep:
            continue
        dst = out.create_sheet(ws.title)
        date_col = None
        for i, row in enumerate(ws.iter_rows()):
            if i == 0:
                keys = [_key(c.value) for c in row]
                date_col = next((keys.index(h) for h in DATE_HEADERS if h in keys), None)
            elif date_col is not None and date_col < len(row):
                year = _year(row[date_col].value)
                if year is not None and year < min_year:
                    continue
            # Plain values are much faster to write; wrap only formatted cells.
            cells: list[object] = []
            for c in row:
                value = getattr(c, "value", None)
                fmt = getattr(c, "number_format", "General")
                if value is None or fmt == "General":
                    cells.append(value)
                else:
                    cell = WriteOnlyCell(dst, value=value)
                    cell.number_format = fmt
                    cells.append(cell)
            dst.append(cells)
    buf = io.BytesIO()
    out.save(buf)
    return buf.getvalue()
