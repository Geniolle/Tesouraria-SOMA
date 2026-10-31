"""Canonical source mappings reused from the existing transfer processes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from src.gmail_to_sheets.processes.verbo_cafe.config import PAGAMENTOS, VENDAS

from .engine import normalize_amount


@dataclass(frozen=True)
class OriginSpec:
    process: str
    source_sheet: str
    spreadsheet: str
    required_headers: frozenset[str]
    adapt: Callable[[dict[str, Any]], dict[str, Any]]


def _canonical(
    row: dict[str, Any], *, date_field: str, description: object, amount_field: str
) -> dict[str, Any]:
    amount: Decimal | None
    try:
        amount = normalize_amount(row.get(amount_field))
    except ValueError:
        amount = None
    return {
        "ID_INTERNO": str(row.get("ID_INTERNO") or "").strip(),
        "DATA MOV.": row.get(date_field),
        "DATA VALOR": row.get("DATA VALOR"),
        "PERÍODO EXTRATO": row.get("PERÍODO EXTRATO") or row.get("PERÍODO"),
        "NÚMERO EXTRATO": row.get("NÚMERO EXTRATO") or row.get("Nº EXTRATO"),
        "DESCRIÇÃO": str(description or "").strip(),
        "IMPORTÂNCIA": amount,
        "DOC. SOMA": str(row.get("DOC. SOMA") or "").strip(),
    }


def _t_extrato(row: dict[str, Any]) -> dict[str, Any]:
    return _canonical(
        row,
        date_field="DATA MOV.",
        description=row.get("DESCRIÇÃO"),
        amount_field="IMPORTÂNCIA",
    )


def _dizimos(row: dict[str, Any]) -> dict[str, Any]:
    number = str(row.get("NÚMERO DOCUMENTO") or "").strip()
    description = (
        f"{number} - DÍZIMOS E OFERTAS (CULTO)"
        if number
        else "DÍZIMOS E OFERTAS (CULTO)"
    )
    return _canonical(row, date_field="DATA", description=description, amount_field="VALOR")


def _saidas(row: dict[str, Any]) -> dict[str, Any]:
    return _canonical(
        row,
        date_field="DATA",
        description=row.get("DESCRIÇÃO DA COMPRA"),
        amount_field="VALOR DA COMPRA",
    )


def _verbo(row: dict[str, Any], amount_field: str) -> dict[str, Any]:
    description = f"{str(row.get('TIPO') or '').strip()} {str(row.get('ID_INTERNO') or '').strip()}".strip()
    return _canonical(row, date_field="DATA", description=description, amount_field=amount_field)


ORIGIN_SPECS = {
    "T_EXTRATO": OriginSpec(
        "T_EXTRATO",
        "T_EXTRATO",
        "main",
        frozenset({"ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA"}),
        _t_extrato,
    ),
    "DÍZIMOS/OFERTAS": OriginSpec(
        "DÍZIMOS/OFERTAS",
        "DÍZIMOS/OFERTAS",
        "main",
        frozenset({"ID_INTERNO", "DATA", "NÚMERO DOCUMENTO", "VALOR"}),
        _dizimos,
    ),
    "SAÍDAS": OriginSpec(
        "SAÍDAS",
        "SAÍDAS",
        "main",
        frozenset({"ID_INTERNO", "DATA", "DATA VALOR", "DESCRIÇÃO DA COMPRA", "VALOR DA COMPRA"}),
        _saidas,
    ),
    VENDAS.processo_tag: OriginSpec(
        VENDAS.processo_tag,
        VENDAS.source_sheet,
        "verbo_cafe",
        frozenset({VENDAS.id_field, VENDAS.data_field, VENDAS.tipo_field, VENDAS.amount_field}),
        lambda row: _verbo(row, VENDAS.amount_field),
    ),
    PAGAMENTOS.processo_tag: OriginSpec(
        PAGAMENTOS.processo_tag,
        PAGAMENTOS.source_sheet,
        "verbo_cafe",
        frozenset({PAGAMENTOS.id_field, PAGAMENTOS.data_field, PAGAMENTOS.tipo_field, PAGAMENTOS.amount_field}),
        lambda row: _verbo(row, PAGAMENTOS.amount_field),
    ),
}


def canonicalize_source(spec: OriginSpec, row: dict[str, Any]) -> dict[str, Any]:
    return spec.adapt(row)
