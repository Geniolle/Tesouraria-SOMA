"""Shared helpers for the extrato transfer service."""

from __future__ import annotations

import unicodedata
from datetime import datetime


def normalize_text(text: str) -> str:
    """Normalize text for ID and duplicate comparisons."""
    if not text:
        return ""
    text = str(text).replace(" ", "").upper()
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def parse_amount(value: str) -> float:
    """Parse a number that may use comma as decimal separator."""
    if not value:
        return 0.0
    try:
        return float(str(value).strip().replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def format_number(value: float) -> str:
    """Format a float using comma decimal separator."""
    return f"{value:.2f}".replace(".", ",")


def get_month_text(data_str: str, meses: list[str]) -> str:
    """Extract the month name from a DD/MM/YYYY string."""
    if not data_str:
        return ""
    try:
        date_obj = datetime.strptime(str(data_str).strip(), "%d/%m/%Y")
        return meses[date_obj.month - 1]
    except (ValueError, IndexError):
        return ""


def get_index(column_name: str, indices: dict) -> int | None:
    """Get a column index by normalized column name."""
    return indices.get(column_name.upper())


def get_cell_value(row: list, column_name: str, indices: dict) -> str:
    """Get a cell value from a row by column name."""
    idx = get_index(column_name, indices)
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx]).strip()


def set_cell_value(row: list, column_name: str, value: str, indices: dict) -> None:
    """Set a cell value in a row by column name."""
    idx = get_index(column_name, indices)
    if idx is not None and idx < len(row):
        row[idx] = value


def load_existing_ids(sheets_client, spreadsheet_id: str, target_sheet: str, target_indices: dict) -> set[str]:
    """Load existing normalized IDs from the target sheet."""
    range_name = sheets_client.get_data_range(spreadsheet_id, target_sheet)
    if not isinstance(range_name, str) or not range_name:
        range_name = f"{target_sheet}!A2:Z99999"
    result = sheets_client.service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()

    rows = result.get("values", [])
    id_idx = target_indices.get("ID_INTERNO")
    if id_idx is None:
        return set()

    existing_ids: set[str] = set()
    for row in rows:
        if id_idx < len(row) and row[id_idx]:
            existing_ids.add(normalize_text(str(row[id_idx])))
    return existing_ids


def build_target_row(
    source_row: list,
    source_indices: dict,
    target_indices: dict,
    target_header_count: int,
    meses: list[str],
) -> list:
    """Build a target row for CONTAORDEM."""
    row = [""] * target_header_count

    data_mov = get_cell_value(source_row, "DATA MOV.", source_indices)
    desc = get_cell_value(source_row, "DESCRIÇÃO", source_indices)
    valor = get_cell_value(source_row, "IMPORTÂNCIA", source_indices)
    tipo = get_cell_value(source_row, "TIPO", source_indices)
    id_interno = get_cell_value(source_row, "ID_INTERNO", source_indices)

    set_cell_value(row, "DATA MOV.", data_mov, target_indices)
    set_cell_value(row, "DESCRIÇÃO", normalize_text(desc), target_indices)
    set_cell_value(row, "IMPORTÂNCIA", format_number(abs(parse_amount(valor))), target_indices)
    set_cell_value(row, "TIPO", tipo, target_indices)
    set_cell_value(row, "PERÍODO", get_month_text(data_mov, meses), target_indices)
    set_cell_value(row, "PROCESSO", "T_EXTRATO", target_indices)
    set_cell_value(row, "ID_INTERNO", id_interno, target_indices)
    return row


def prepare_all_data(
    source_rows: list[list],
    source_ids_set: set[str] | None,
    source_indices: dict,
    target_indices: dict,
    target_header_count: int,
    existing_ids: set[str],
    meses: list[str],
) -> dict:
    """Prepare target rows, status updates and statistics for batch writing."""
    target_rows = []
    status_updates = {}
    stats = {
        "transferred": 0,
        "already_exists": 0,
        "empty_id": 0,
        "with_status": 0,
        "total_processed": 0,
    }

    for idx, source_row in enumerate(source_rows):
        row_number = idx + 2
        id_interno = get_cell_value(source_row, "ID_INTERNO", source_indices)
        id_normalized = normalize_text(id_interno)

        if source_ids_set is not None and id_normalized not in source_ids_set:
            continue

        stats["total_processed"] += 1

        status_idx = get_index("STATUS", source_indices)
        if status_idx is not None and status_idx < len(source_row):
            status_val = str(source_row[status_idx]).strip()
            if status_val:
                stats["with_status"] += 1
                continue

        if not id_interno:
            status_updates[row_number] = "Erro: ID_INTERNO vazio"
            stats["empty_id"] += 1
            continue

        if id_normalized in existing_ids:
            status_updates[row_number] = "Ja existe"
            stats["already_exists"] += 1
            continue

        try:
            target_row = build_target_row(
                source_row,
                source_indices,
                target_indices,
                target_header_count,
                meses,
            )
            target_rows.append(target_row)
            existing_ids.add(id_normalized)
            status_updates[row_number] = "Transferido"
            stats["transferred"] += 1
        except Exception as exc:  # pragma: no cover - defensive guard
            status_updates[row_number] = f"Erro: {str(exc)[:40]}"

    return {
        "target_rows": target_rows,
        "status_updates": status_updates,
        "stats": stats,
    }
