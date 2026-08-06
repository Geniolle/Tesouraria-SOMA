"""
Matching Service

Matches transactions from CONTAORDEM with document definitions from CONSTANTES.
Implements "de-para" logic: fills DOC.SOMA, DESCRIÇÃO SOMA, and additional fields.
"""

import logging
import unicodedata
from datetime import datetime
from typing import Any, Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class MatchingService:
    """Service to match CONTAORDEM records with CONSTANTES definitions."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        source_sheet: str = "CONTAORDEM",
        reference_sheet: str = "CONSTANTES",
        timezone: str = "Europe/Lisbon",
    ):
        """
        Initialize matching service.

        Args:
            sheets_client: Authenticated Sheets client
            spreadsheet_id: Target spreadsheet ID
            source_sheet: Sheet with transactions to match (CONTAORDEM)
            reference_sheet: Sheet with document definitions (CONSTANTES)
            timezone: Timezone for timestamp
        """
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.reference_sheet = reference_sheet
        self.timezone = timezone

        # Load headers and indices
        self.source_headers = self._load_headers(source_sheet)
        self.ref_headers = self._load_headers(reference_sheet)

        self.source_indices = self._map_columns(self.source_headers)
        self.ref_indices = self._map_columns(self.ref_headers)

        # Validate required columns
        self._validate_columns()

        # Fields to copy from CONSTANTES to CONTAORDEM
        self.fields_to_copy = [
            "PLANO DE CONTA",
            "CENTRO DE CUSTO",
            "FORMA DE PAGAMENTO",
            "CAIXA",
            "CAIXA SAIDA"
        ]

    def _load_headers(self, sheet_name: str) -> list[str]:
        """Load headers from sheet."""
        try:
            headers = self.sheets_client.get_headers(self.spreadsheet_id, sheet_name)
            logger.info(f"Loaded {len(headers)} columns from {sheet_name}")
            return headers
        except Exception as e:
            logger.error(f"Failed to load headers from {sheet_name}: {e}")
            raise

    def _map_columns(self, headers: list[str]) -> dict[str, int]:
        """Map column names to indices."""
        indices = {}
        for idx, header in enumerate(headers):
            key = str(header).strip().upper()
            indices[key] = idx
        return indices

    def _validate_columns(self) -> None:
        """Validate required columns exist in both sheets."""
        required_source = ["DOC. SOMA", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "DESCRIÇÃO SOMA", "DATA MOV."]
        required_ref = ["TEXTO", "TIPO", "DESCRIÇÃO SOMA", "DOC. SOMA"]

        missing_source = [col for col in required_source if col.upper() not in self.source_indices]
        missing_ref = [col for col in required_ref if col.upper() not in self.ref_indices]

        if missing_source:
            raise RuntimeError(f"Missing columns in {self.source_sheet}: {missing_source}")
        if missing_ref:
            raise RuntimeError(f"Missing columns in {self.reference_sheet}: {missing_ref}")

        logger.info("✓ All required columns found in both sheets")

    def process_matching(self) -> dict:
        """
        Process matching between CONTAORDEM and CONSTANTES.

        Returns:
            Matching statistics
        """
        try:
            logger.info(f"Starting matching from {self.source_sheet} with {self.reference_sheet}")

            # Load data
            source_data = self._load_data(self.source_sheet)
            ref_data = self._load_data(self.reference_sheet)

            logger.info(f"Loaded {len(source_data)} rows from {self.source_sheet}")
            logger.info(f"Loaded {len(ref_data)} rows from {self.reference_sheet}")

            stats = {
                "total_processed": 0,
                "eligible_rows": 0,
                "matched": 0,
                "no_match": 0,
                "errors": [],
            }

            # Build sequential state for daily numbering
            seq_state: dict[str, dict[str, Any]] = {}

            # First pass: load existing sequences
            self._build_sequential_state(source_data, seq_state)

            # Second pass: process matching
            updates = []

            for idx, source_row in enumerate(source_data):
                row_number = idx + 2  # +1 for header, +1 for 1-indexed
                stats["total_processed"] += 1

                # Check eligibility
                doc_soma_current = self._get_cell(source_row, "DOC. SOMA")
                if not self._is_eligible(doc_soma_current):
                    continue

                stats["eligible_rows"] += 1

                # Try to match
                match_result = self._find_match(source_row, ref_data, seq_state)

                if match_result:
                    stats["matched"] += 1
                    updates.append({
                        "row_number": row_number,
                        "source_data": source_row,
                        "match": match_result,
                        "ref_row_idx": match_result["ref_row_idx"]
                    })
                    logger.info(f"Row {row_number}: Match found with DOC.SOMA '{match_result['doc_soma']}'")
                else:
                    stats["no_match"] += 1
                    logger.warning(f"Row {row_number}: No match found")

            # Apply updates
            self._apply_updates(source_data, ref_data, updates)

            # Write back
            if source_data:
                self._write_data(self.source_sheet, source_data)
            if ref_data:
                self._write_timestamp(self.reference_sheet, ref_data)

            # Sort by DATA MOV. (descending)
            self._sort_by_date(self.source_sheet)

            logger.info(f"Matching completed: {stats['matched']} matched, {stats['no_match']} no match")
            return stats

        except Exception as e:
            logger.error(f"Matching process failed: {e}")
            raise

    def _load_data(self, sheet_name: str) -> list[list]:
        """Load all data rows from sheet."""
        try:
            range_name = f"{sheet_name}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            # Ensure all rows have same number of columns
            max_cols = max((len(row) for row in rows), default=0)
            normalized = []
            for row in rows:
                normalized_row = list(row) + [""] * (max_cols - len(row))
                normalized.append(normalized_row)

            return normalized

        except Exception as e:
            logger.error(f"Failed to load data from {sheet_name}: {e}")
            raise

    def _write_data(self, sheet_name: str, data: list[list]) -> None:
        """Write data back to sheet."""
        try:
            if not data:
                return

            num_rows = len(data)

            range_name = f"{sheet_name}!A2:Z99999"
            self.sheets_client.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": data}
            ).execute()

            logger.info(f"Wrote {num_rows} rows to {sheet_name}")

        except Exception as e:
            logger.error(f"Failed to write data to {sheet_name}: {e}")
            raise

    def _write_timestamp(self, sheet_name: str, data: list[list]) -> None:
        """Write timestamp column back to sheet."""
        try:
            timestamp_idx = self._get_index("TIMESTAMP", self.ref_indices)
            if timestamp_idx is None:
                return

            timestamp_col = [[row[timestamp_idx]] for row in data]
            col_letter = self._number_to_column(timestamp_idx + 1)
            range_name = f"{sheet_name}!{col_letter}2:{col_letter}99999"

            self.sheets_client.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": timestamp_col}
            ).execute()

            logger.info(f"Updated timestamp column in {sheet_name}")

        except Exception as e:
            logger.warning(f"Failed to write timestamp: {e}")

    def _sort_by_date(self, sheet_name: str) -> None:
        """Sort sheet by DATA MOV. (descending)."""
        try:
            data_idx = self._get_index("DATA MOV.", self.source_indices)
            if data_idx is None:
                return

            # Get last row
            last_row = self.sheets_client.get_last_row(self.spreadsheet_id, sheet_name)
            if last_row <= 2:
                return

            # Create sort request
            request = {
                "sortRange": {
                    "range": {
                        "sheetId": self._get_sheet_id(sheet_name),
                        "startRowIndex": 1,  # Skip header
                        "endRowIndex": last_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(self.source_headers)
                    },
                    "sortSpecs": [
                        {
                            "dimensionIndex": data_idx,
                            "sortOrder": "DESCENDING"
                        }
                    ]
                }
            }

            self.sheets_client.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [request]}
            ).execute()

            logger.info(f"Sorted {sheet_name} by DATA MOV. (descending)")

        except Exception as e:
            logger.warning(f"Failed to sort sheet: {e}")

    def _build_sequential_state(self, data: list[list], seq_state: dict) -> None:
        """Build state of existing sequences."""
        desc_soma_idx = self._get_index("DESCRIÇÃO SOMA", self.source_indices)
        data_mov_idx = self._get_index("DATA MOV.", self.source_indices)

        if desc_soma_idx is None or data_mov_idx is None:
            return

        for row in data:
            desc_soma = self._get_cell_by_idx(row, desc_soma_idx)
            data_mov = self._get_cell_by_idx(row, data_mov_idx)

            if not desc_soma or not data_mov:
                continue

            parsed = self._split_description_sequential(desc_soma)
            base = parsed["base"]
            n = parsed["n"]

            if not base or not n:
                continue

            dia_key = self._get_day_key(data_mov)
            base_key = self._normalize_text(base)

            if not dia_key or not base_key:
                continue

            state_key = f"{dia_key}||{base_key}"

            if state_key not in seq_state:
                seq_state[state_key] = {
                    "used": {},
                    "max": 0,
                    "base_example": base,
                    "day_display": self._format_day_display(data_mov)
                }

            seq_state[state_key]["used"][n] = True
            if n > seq_state[state_key]["max"]:
                seq_state[state_key]["max"] = n

    def _find_match(self, source_row: list, ref_data: list[list], seq_state: dict) -> Optional[dict]:
        """Find matching reference row for source row."""
        desc_idx = self._get_index("DESCRIÇÃO", self.source_indices)
        tipo_idx = self._get_index("TIPO", self.source_indices)
        valor_idx = self._get_index("IMPORTÂNCIA", self.source_indices)
        data_mov_idx = self._get_index("DATA MOV.", self.source_indices)

        ref_texto_idx = self._get_index("TEXTO", self.ref_indices)
        ref_tipo_idx = self._get_index("TIPO", self.ref_indices)
        ref_valor_idx = self._get_index("VALOR", self.ref_indices)
        ref_doc_soma_idx = self._get_index("DOC. SOMA", self.ref_indices)
        ref_desc_soma_idx = self._get_index("DESCRIÇÃO SOMA", self.ref_indices)

        if any(idx is None for idx in [desc_idx, tipo_idx, valor_idx, data_mov_idx,
                                        ref_texto_idx, ref_tipo_idx, ref_doc_soma_idx, ref_desc_soma_idx]):
            return None

        desc_norm = self._normalize_text(self._get_cell_by_idx(source_row, desc_idx))
        tipo = self._get_cell_by_idx(source_row, tipo_idx).upper()
        valor = self._parse_amount(self._get_cell_by_idx(source_row, valor_idx))
        data_mov = self._get_cell_by_idx(source_row, data_mov_idx)

        for ref_idx, ref_row in enumerate(ref_data):
            ref_texto = self._get_cell_by_idx(ref_row, ref_texto_idx)
            ref_tipo = self._get_cell_by_idx(ref_row, ref_tipo_idx).upper()
            ref_valor_raw = self._get_cell_by_idx(ref_row, ref_valor_idx)

            # Text matching (both directions)
            ref_texto_norm = self._normalize_text(ref_texto)
            if not ref_texto_norm:
                continue

            text_ok = (desc_norm in ref_texto_norm) or (ref_texto_norm in desc_norm)

            # Type matching
            type_ok = tipo == ref_tipo

            # Value matching (if specified in reference)
            value_ok = True
            if ref_valor_raw and ref_valor_raw.strip():
                ref_valor = self._parse_amount(ref_valor_raw)
                value_ok = abs(valor - ref_valor) < 0.01

            if text_ok and type_ok and value_ok:
                # Found a match!
                doc_soma = self._get_cell_by_idx(ref_row, ref_doc_soma_idx)
                desc_soma_base = self._get_cell_by_idx(ref_row, ref_desc_soma_idx)

                # Generate sequential description for the day
                desc_soma_final = self._generate_sequential_description(
                    desc_soma_base, data_mov, seq_state
                )

                return {
                    "ref_row_idx": ref_idx,
                    "doc_soma": doc_soma,
                    "desc_soma": desc_soma_final,
                    "desc_soma_base": desc_soma_base,
                    "ref_texto": ref_texto,
                    "ref_tipo": ref_tipo,
                    "ref_valor": ref_valor_raw,
                    "timestamp": self._get_timestamp()
                }

        return None

    def _apply_updates(self, source_data: list[list], ref_data: list[list], updates: list) -> None:
        """Apply matched updates to source and reference data."""
        doc_soma_idx = self._get_index("DOC. SOMA", self.source_indices)
        desc_soma_idx = self._get_index("DESCRIÇÃO SOMA", self.source_indices)
        timestamp_idx = self._get_index("TIMESTAMP", self.ref_indices)

        for update in updates:
            source_row = update["source_data"]
            match = update["match"]
            ref_row_idx = update["ref_row_idx"]

            # Update source row
            if doc_soma_idx is not None:
                source_row[doc_soma_idx] = match["doc_soma"]
            if desc_soma_idx is not None:
                source_row[desc_soma_idx] = match["desc_soma"]

            # Copy additional fields
            for field in self.fields_to_copy:
                ref_field_idx = self._get_index(field, self.ref_indices)
                source_field_idx = self._get_index(field, self.source_indices)

                if ref_field_idx is not None and source_field_idx is not None:
                    source_row[source_field_idx] = ref_data[ref_row_idx][ref_field_idx]

            # Update reference timestamp
            if timestamp_idx is not None:
                ref_data[ref_row_idx][timestamp_idx] = match["timestamp"]

    def _generate_sequential_description(self, desc_base: str, data_mov: str, seq_state: dict) -> str:
        """Generate description with daily sequential number."""
        desc_base = str(desc_base or "").strip()
        if not desc_base:
            return ""

        parsed = self._split_description_sequential(desc_base)
        base = parsed["base"] or desc_base

        dia_key = self._get_day_key(data_mov)
        base_key = self._normalize_text(base)

        if not dia_key or not base_key:
            return desc_base

        state_key = f"{dia_key}||{base_key}"

        if state_key not in seq_state:
            seq_state[state_key] = {
                "used": {},
                "max": 0,
                "base_example": base,
                "day_display": self._format_day_display(data_mov)
            }

        state = seq_state[state_key]
        next_n = state["max"] + 1

        while next_n <= 999 and next_n in state["used"]:
            next_n += 1

        if next_n > 999:
            raise RuntimeError(f"Sequential limit exceeded for '{base}'")

        state["used"][next_n] = True
        state["max"] = next_n

        n_fmt = str(next_n).zfill(3)
        return f"{base} N{n_fmt}".strip()

    # Helper methods

    def _get_index(self, column_name: str, indices: dict) -> Optional[int]:
        """Get column index by name."""
        return indices.get(column_name.upper())

    def _get_cell(self, row: list, column_name: str) -> str:
        """Get cell value by column name."""
        idx = self._get_index(column_name, self.source_indices)
        return self._get_cell_by_idx(row, idx)

    def _get_cell_by_idx(self, row: list, idx: Optional[int]) -> str:
        """Get cell value by index."""
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    def _is_eligible(self, doc_soma: str) -> bool:
        """Check if row is eligible for processing."""
        doc_soma_str = str(doc_soma or "").strip()
        if not doc_soma_str:
            return True
        return doc_soma_str.upper() == "EM ERRO"

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text: remove accents and uppercase."""
        if not text:
            return ""

        text = str(text).replace(" ", "").upper()
        normalized = unicodedata.normalize("NFD", text)
        without_accents = "".join(
            char for char in normalized if unicodedata.category(char) != "Mn"
        )
        return without_accents

    @staticmethod
    def _split_description_sequential(desc: str) -> dict:
        """Split description into base and sequential number."""
        import re

        desc_str = str(desc or "").strip()
        if not desc_str:
            return {"base": "", "n": None}

        match = re.match(r"^(.*?)\s+N(\d{3})$", desc_str, re.IGNORECASE)
        if match:
            return {
                "base": match.group(1).strip(),
                "n": int(match.group(2))
            }

        return {"base": desc_str, "n": None}

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Parse amount with comma as decimal separator."""
        if not value:
            return 0.0

        try:
            value_str = str(value).strip().replace(",", ".")
            return float(value_str)
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _get_day_key(data_mov: str) -> str:
        """Get date key (YYYY-MM-DD)."""
        if not data_mov:
            return ""

        try:
            # Try DD/MM/YYYY format
            from datetime import datetime
            date_obj = datetime.strptime(str(data_mov).strip(), "%d/%m/%Y")
            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _format_day_display(data_mov: str) -> str:
        """Format date for display (DD/MM/YYYY)."""
        if not data_mov:
            return ""

        try:
            from datetime import datetime
            date_obj = datetime.strptime(str(data_mov).strip(), "%d/%m/%Y")
            return date_obj.strftime("%d/%m/%Y")
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp."""
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    @staticmethod
    def _number_to_column(col_num: int) -> str:
        """Convert column number to letter."""
        col_letter = ""
        while col_num > 0:
            col_num -= 1
            col_letter = chr(65 + col_num % 26) + col_letter
            col_num //= 26
        return col_letter

    def _get_sheet_id(self, sheet_name: str) -> int:
        """Get sheet ID by name."""
        try:
            spreadsheet = self.sheets_client.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()

            sheets = spreadsheet.get("sheets", [])
            for sheet in sheets:
                if sheet["properties"]["title"] == sheet_name:
                    return sheet["properties"]["sheetId"]

            return 0
        except Exception as e:
            logger.warning(f"Failed to get sheet ID: {e}")
            return 0
