"""Verbo Café sales and product costs from the AppVerboCafé spreadsheet.

Same shape as bookshop.py so the page renders both P&L cards with one
function: per-sale amounts and items, plus the average unit cost per item key
(product EAN or "PACK:<menu>"). Donated purchases (FORMA DE PAGAMENTO =
DOAÇÃO) cost 0, so their margin is 100%. Customer names never leave the server.
"""

import datetime as dt
from typing import Any

from bookshop import _isbn as _ean
from bookshop import _num, _table
from googleapiclient.discovery import build


def fetch_cafe(credentials: Any, spreadsheet_id: str, min_year: int | None) -> dict:
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    totals: dict[str, list[float]] = {}
    list_price: dict[str, float] = {}
    for r in _table(sheets, spreadsheet_id, "VC_COMPRAS"):
        ean = _ean(r.get("EAN", ""))
        if not ean:
            continue
        qty = _num(r.get("QUANTIDADE DE UNIDADES", "")) or _num(r.get("QUANTIDADE", ""))
        donated = r.get("FORMA DE PAGAMENTO", "").strip().upper() == "DOAÇÃO"
        unit = 0.0 if donated else _num(r.get("VALOR DA UNIDADE", ""))
        if qty:
            t = totals.setdefault(ean, [0.0, 0.0])
            t[0] += qty * unit
            t[1] += qty
        if _num(r.get("PREÇO DE VENDA", "")):
            list_price[ean] = _num(r.get("PREÇO DE VENDA", ""))
    costs = {ean: v / q for ean, (v, q) in totals.items() if q}

    # Menus: cost = sum of their products' unit costs; price falls back to PREÇO FINAL.
    pack_price: dict[str, float] = {}
    for r in _table(sheets, spreadsheet_id, "VC_PACK"):
        name = r.get("MENU COMBINADO", "").strip().upper()
        if not name:
            continue
        cost = sum(
            _num(r.get(f"QUANTIDADE{k}", "")) * costs.get(_ean(r.get(f"EAN{k}", "")), 0.0)
            for k in range(1, 11)
        )
        costs["PACK:" + name] = cost
        pack_price[name] = _num(r.get("PREÇO FINAL", ""))

    sales, donations = [], []
    for r in _table(sheets, spreadsheet_id, "VC_VENDAS"):
        if r.get("FINALIZAR COMPRA?", "").strip().upper() != "TRUE":
            continue
        try:
            day = dt.datetime.strptime(r.get("DATA", "").strip()[:10], "%d/%m/%Y").date()
        except ValueError:
            continue
        if min_year and day.year < min_year:
            continue
        if r.get("TIPO", "").strip().upper() == "DOAÇÃO":
            amount = _num(r.get("MONTANTE DOAÇÃO", "")) or _num(r.get("VALOR A PAGAR", ""))
            donations.append({"date": day.isoformat(), "amount": amount})
            continue
        items = []
        for k in range(1, 6):
            menu, qty = r.get(f"MENU BOX{k}", "").strip(), _num(r.get(f"QUANTIDADE BOX{k}", ""))
            if menu and qty:
                price = _num(r.get(f"PREÇO BOX{k}", "")) or pack_price.get(menu.upper(), 0.0)
                items.append(
                    {"key": "PACK:" + menu.upper(), "title": menu, "qty": qty, "price": price}
                )
            ean, qty = _ean(r.get(f"EAN{k}", "")), _num(r.get(f"QUANTIDADE {k}", ""))
            if ean and qty:
                price = _num(r.get(f"PREÇO UNIDADE {k}", "")) or list_price.get(ean, 0.0)
                title = r.get(f"PRODUTO {k}", "").split(":")[0].strip()
                items.append({"key": ean, "title": title, "qty": qty, "price": price})
        sales.append(
            {
                "date": day.isoformat(),
                "payment": r.get("FORMA DE PAGAMENTO", "").strip().upper(),
                "total": _num(r.get("VALOR A PAGAR", "")),
                "items": items,
            }
        )
    rounded = {k: round(v, 4) for k, v in costs.items()}
    return {"costs": rounded, "sales": sales, "donations": donations}
