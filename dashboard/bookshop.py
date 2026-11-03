"""Bookshop sales and purchase costs from the AppVerboShop spreadsheet.

Returns only what the P&L card needs: per-sale amounts and items, and the
average purchase cost per ISBN. Customer name, phone and email never leave
the server.
"""

import datetime as dt
import re
from typing import Any

from googleapiclient.discovery import build


def _num(value: str) -> float:
    text = str(value or "").replace("€", "").replace("%", "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _isbn(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _table(sheets: Any, spreadsheet_id: str, name: str) -> list[dict[str, str]]:
    rows = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{name}'")
        .execute()
        .get("values", [])
    )
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    return [{h: (r[i] if i < len(r) else "") for i, h in enumerate(head)} for r in rows[1:]]


def fetch_bookshop(credentials: Any, spreadsheet_id: str, min_year: int | None) -> dict:
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    # Weighted average cost per ISBN (VALOR UNITÁRIO is already net of the supplier discount).
    totals: dict[str, list[float]] = {}
    for r in _table(sheets, spreadsheet_id, "DB_COMPRAS"):
        isbn, qty = _isbn(r.get("ISBN", "")), _num(r.get("QUANTIDADE", ""))
        if isbn and qty:
            t = totals.setdefault(isbn, [0.0, 0.0])
            t[0] += qty * _num(r.get("VALOR UNITÁRIO", ""))
            t[1] += qty
    costs = {isbn: round(v / q, 4) for isbn, (v, q) in totals.items() if q}

    sales = []
    for r in _table(sheets, spreadsheet_id, "DB_VENDAS"):
        if r.get("FINALIZAR COMPRA?", "").strip().upper() != "TRUE":
            continue
        try:
            day = dt.datetime.strptime(r.get("DATA DA VENDA", "").strip()[:10], "%d/%m/%Y").date()
        except ValueError:
            continue
        if min_year and day.year < min_year:
            continue
        items = []
        for k in range(1, 6):
            qty = _num(r.get(f"QUANTIDADE {k}", ""))
            if qty:
                items.append(
                    {
                        "key": _isbn(r.get(f"ISBN{k}", "")),
                        "title": r.get(f"TÍTULO {k}", "").strip(),
                        "qty": qty,
                        "price": _num(r.get(f"PREÇO DE CAPA {k}", "")),
                    }
                )
        sales.append(
            {
                "date": day.isoformat(),
                "payment": r.get("FORMA DE PAGAMENTO", "").strip().upper(),
                "total": _num(r.get("TOTAL A PAGAR", "")),
                "items": items,
            }
        )
    return {"costs": costs, "sales": sales}
