"""Shared helpers for the extrato sheets writer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from src.gmail_to_sheets.models.transaction import Transaction
from src.gmail_to_sheets.validators.deduplication import DeduplicationService


def load_headers(sheets_client, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Load headers from sheet."""
    return sheets_client.get_headers(spreadsheet_id, sheet_name)


def map_columns(headers: list[str]) -> dict[str, int]:
    """Map column names to 0-indexed positions."""
    indices: dict[str, int] = {}
    for idx, header in enumerate(headers):
        indices[str(header).strip()] = idx
    return indices


def load_last_sequence(sheets_client, spreadsheet_id: str, sheet_name: str, column_indices: dict) -> int:
    """Load the last ID_INTERNO sequence number from sheet."""
    id_idx = column_indices.get("ID_INTERNO")
    if id_idx is None:
        return 0

    range_name = sheets_client.get_data_range(spreadsheet_id, sheet_name)
    if not isinstance(range_name, str) or not range_name:
        range_name = f"{sheet_name}!A2:Z99999"
    result = sheets_client.service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return 0

    max_sequence = 0
    for row in rows:
        if id_idx < len(row) and row[id_idx]:
            id_interno = str(row[id_idx]).strip()
            if id_interno.startswith("EXT"):
                try:
                    max_sequence = max(max_sequence, int(id_interno[3:]))
                except (ValueError, IndexError):
                    continue
    return max_sequence


def load_existing_dedup_keys(
    sheets_client,
    spreadsheet_id: str,
    sheet_name: str,
    column_indices: dict,
    dedup_service: DeduplicationService,
) -> None:
    """Load existing transactions for deduplication."""
    range_name = sheets_client.get_data_range(spreadsheet_id, sheet_name)
    if not isinstance(range_name, str) or not range_name:
        range_name = f"{sheet_name}!A2:Z99999"
    result = sheets_client.service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return

    data_mov_idx = column_indices.get("DATA MOV.")
    desc_idx = column_indices.get("DESCRIÇÃO")
    valor_idx = column_indices.get("IMPORTÂNCIA")

    if data_mov_idx is None or desc_idx is None or valor_idx is None:
        return

    existing_keys = set()
    for row in rows:
        try:
            if data_mov_idx < len(row) and desc_idx < len(row) and valor_idx < len(row):
                data_mov = str(row[data_mov_idx]).strip() if row[data_mov_idx] else ""
                descricao = str(row[desc_idx]).strip() if row[desc_idx] else ""
                valor = str(row[valor_idx]).strip() if row[valor_idx] else ""
                if data_mov and descricao and valor:
                    existing_keys.add(f"{data_mov}|{descricao}|{valor}")
        except Exception:
            continue

    dedup_service.add_existing(existing_keys)


def parse_opening_balance(opening_balance) -> Decimal:
    """Validate and normalize the opening balance."""
    if opening_balance is None:
        raise ValueError("opening_balance is required")
    if isinstance(opening_balance, str) and not opening_balance.strip():
        raise ValueError("opening_balance is required")

    try:
        if isinstance(opening_balance, str):
            return Decimal(opening_balance.strip().replace(",", "."))
        return Decimal(str(opening_balance))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"Invalid opening_balance: {opening_balance}") from exc


def format_decimal(value: Decimal | float | str) -> str:
    """Format a numeric value using comma decimals."""
    return format(Decimal(str(value)), ".2f").replace(".", ",")


def transaction_to_row(
    txn: Transaction,
    headers: list[str],
    column_indices: dict,
    saldo_contabilistico=None,
    sequencial: int = 0,
) -> list:
    """Convert transaction to sheet row with formatting."""
    row = [""] * len(headers)

    try:
        valor_decimal = Decimal(str(txn.valor).replace(",", "."))
        valor_formatado = format_decimal(valor_decimal)
    except (ValueError, TypeError, InvalidOperation):
        valor_formatado = "0,00"

    saldo_formatado = ""
    if saldo_contabilistico is not None:
        try:
            saldo_formatado = format_decimal(saldo_contabilistico)
        except (ValueError, TypeError, InvalidOperation):
            saldo_formatado = "0,00"

    id_interno = txn.id_interno
    if not id_interno and sequencial > 0:
        id_interno = f"EXT{str(sequencial).zfill(10)}"

    column_mapping = {
        "DATA MOV.": txn.data_mov,
        "DATA VALOR": txn.data_valor,
        "DESCRIÇÃO": txn.descricao,
        "IMPORTÂNCIA": valor_formatado,
        "TIPO": txn.tipo,
        "TIMESTAMP": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "SALDO CONTABILÍSTICO": saldo_formatado,
        "ID_INTERNO": id_interno,
    }

    for col_name, value in column_mapping.items():
        idx = column_indices.get(col_name)
        if idx is not None:
            row[idx] = value

    return row


def write_closing_balance(
    sheets_client,
    spreadsheet_id: str,
    sheet_name: str,
    column_indices: dict,
    row_number: int,
    balance: str,
) -> None:
    """Write closing balance to specific row."""
    saldo_idx = column_indices.get("SALDO CONTABILÍSTICO", 6)
    if saldo_idx is None:
        return
    sheets_client.update_cell(
        spreadsheet_id,
        sheet_name,
        row_number,
        saldo_idx + 1,
        balance,
    )
