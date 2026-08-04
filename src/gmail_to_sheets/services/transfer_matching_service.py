"""
Transfer + Matching Service (Integrated Batch)

Combines transfer and matching in a single optimized pipeline.
Prepares complete CONTAORDEM rows with CONSTANTES data in one batch operation.
"""

import logging
import unicodedata
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.services.batch_writer import BatchWriter


logger = logging.getLogger(__name__)


class TransferMatchingService:
    """
    Integrated service that:
    1. Transfers from T_EXTRATO to CONTAORDEM
    2. Matches with CONSTANTES to fill additional fields
    3. Writes everything in optimized batches
    """

    MESES = [
        "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
        "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"
    ]

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        source_sheet: str = "T_EXTRATO",
        target_sheet: str = "CONTAORDEM",
        reference_sheet: str = "CONSTANTES",
    ):
        """Initialize integrated transfer+matching service."""
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.source_sheet = source_sheet
        self.target_sheet = target_sheet
        self.reference_sheet = reference_sheet

        # Load all headers
        self.source_headers = self._load_headers(source_sheet)
        self.target_headers = self._load_headers(target_sheet)
        self.ref_headers = self._load_headers(reference_sheet)

        self.source_indices = self._map_columns(self.source_headers)
        self.target_indices = self._map_columns(self.target_headers)
        self.ref_indices = self._map_columns(self.ref_headers)

        self._validate_columns()

        # Load reference data for matching
        self.ref_data = self._load_reference_data()
        self.existing_ids = self._load_existing_ids()

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
        """Validate required columns."""
        required = {
            "SOURCE": ["DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "ID_INTERNO", "STATUS"],
            "TARGET": ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "PERÍODO", "PROCESSO", "ID_INTERNO"],
            "REFERENCE": ["TEXTO", "TIPO", "DOC. SOMA", "DESCRIÇÃO SOMA"]
        }

        for sheet_type, cols in required.items():
            if sheet_type == "SOURCE":
                indices = self.source_indices
                sheet_name = self.source_sheet
            elif sheet_type == "TARGET":
                indices = self.target_indices
                sheet_name = self.target_sheet
            else:
                indices = self.ref_indices
                sheet_name = self.reference_sheet

            missing = [col for col in cols if col.upper() not in indices]
            if missing:
                raise RuntimeError(f"Missing columns in {sheet_name}: {missing}")

        logger.info("✓ All columns validated")

    def _load_reference_data(self) -> list[list]:
        """Load reference data for matching."""
        try:
            range_name = f"{self.reference_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            logger.info(f"Loaded {len(rows)} reference rows")
            return rows

        except Exception as e:
            logger.error(f"Failed to load reference data: {e}")
            raise

    def _load_existing_ids(self) -> set:
        """Load existing IDs from target."""
        try:
            range_name = f"{self.target_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            id_idx = self.target_indices.get("ID_INTERNO")

            if id_idx is None:
                return set()

            existing = set()
            for row in rows:
                if id_idx < len(row) and row[id_idx]:
                    existing.add(self._normalize_text(str(row[id_idx])))

            logger.info(f"Loaded {len(existing)} existing IDs")
            return existing

        except Exception as e:
            logger.error(f"Failed to load existing IDs: {e}")
            raise

    def process_with_matching(self) -> dict:
        """
        Execute integrated transfer + matching process.

        Returns:
            Statistics dictionary
        """
        try:
            logger.info("Starting integrated transfer+matching (batch optimized)...")

            # Load source data
            range_name = f"{self.source_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            source_rows = result.get("values", [])
            logger.info(f"Found {len(source_rows)} source rows")

            # Phase 1: Prepare all data with matching
            logger.info("Phase 1: Preparing and matching data...")
            prepared = self._prepare_with_matching(source_rows)

            target_rows = prepared["target_rows"]
            status_updates = prepared["status_updates"]
            stats = prepared["stats"]

            logger.info(f"Prepared: {len(target_rows)} rows, "
                       f"{stats['matched']} matched, "
                       f"{stats['no_match']} without match")

            # Phase 2: Batch write all at once
            if target_rows or status_updates:
                logger.info("Phase 2: Batch writing all data...")
                batch_writer = BatchWriter(self.sheets_client, self.spreadsheet_id)

                try:
                    batch_result = batch_writer.batch_write_with_updates(
                        source_sheet=self.source_sheet,
                        source_data=[],
                        target_sheet=self.target_sheet,
                        target_data=target_rows,
                        status_updates=status_updates
                    )
                    logger.info(f"Batch result: {batch_result}")
                except Exception as e:
                    logger.error(f"Batch write failed: {e}")
                    stats["write_errors"] = str(e)

            logger.info(f"Completed: {stats['transferred']} transferred, "
                       f"{stats['matched']} with matches")

            return stats

        except Exception as e:
            logger.error(f"Process failed: {e}")
            raise

    def _prepare_with_matching(self, source_rows: list[list]) -> dict:
        """
        Prepare all rows with matching in a single pass.

        Returns:
            Dictionary with target_rows, status_updates, and stats
        """
        target_rows = []
        status_updates = {}
        stats = {
            "transferred": 0,
            "already_exists": 0,
            "empty_id": 0,
            "with_status": 0,
            "matched": 0,
            "no_match": 0,
            "total_processed": 0,
        }

        for idx, source_row in enumerate(source_rows):
            row_number = idx + 2
            stats["total_processed"] += 1

            # Check status
            status_idx = self._get_index("STATUS", self.source_indices)
            if status_idx is not None and status_idx < len(source_row):
                if str(source_row[status_idx]).strip():
                    stats["with_status"] += 1
                    continue

            # Get ID
            id_interno = self._get_cell_value(source_row, "ID_INTERNO", self.source_indices)
            id_normalized = self._normalize_text(id_interno)

            if not id_interno:
                status_updates[row_number] = "Erro: ID vazio"
                stats["empty_id"] += 1
                continue

            if id_normalized in self.existing_ids:
                status_updates[row_number] = "Ja existe"
                stats["already_exists"] += 1
                continue

            # Build target row
            try:
                target_row = self._build_target_row(source_row)

                # Try to match with reference data
                match = self._find_match(source_row)
                if match:
                    target_row = self._enrich_with_match(target_row, match)
                    stats["matched"] += 1
                    logger.debug(f"Row {row_number}: Match found")
                else:
                    stats["no_match"] += 1
                    logger.debug(f"Row {row_number}: No match")

                target_rows.append(target_row)
                self.existing_ids.add(id_normalized)
                status_updates[row_number] = "Transferido"
                stats["transferred"] += 1

            except Exception as e:
                status_updates[row_number] = f"Erro: {str(e)[:40]}"
                logger.error(f"Row {row_number}: {e}")

        return {
            "target_rows": target_rows,
            "status_updates": status_updates,
            "stats": stats
        }

    def _find_match(self, source_row: list) -> Optional[dict]:
        """Find matching reference row."""
        desc_norm = self._normalize_text(
            self._get_cell_value(source_row, "DESCRIÇÃO", self.source_indices)
        )
        tipo = self._get_cell_value(source_row, "TIPO", self.source_indices).upper()
        valor = self._parse_amount(
            self._get_cell_value(source_row, "IMPORTÂNCIA", self.source_indices)
        )

        for ref_row in self.ref_data:
            ref_texto = self._get_cell_value(ref_row, "TEXTO", self.ref_indices)
            ref_tipo = self._get_cell_value(ref_row, "TIPO", self.ref_indices).upper()
            ref_valor_raw = self._get_cell_value(ref_row, "VALOR", self.ref_indices)

            # Text matching
            ref_texto_norm = self._normalize_text(ref_texto)
            if not ref_texto_norm:
                continue

            text_ok = (desc_norm in ref_texto_norm) or (ref_texto_norm in desc_norm)
            type_ok = tipo == ref_tipo
            value_ok = True

            if ref_valor_raw and ref_valor_raw.strip():
                ref_valor = self._parse_amount(ref_valor_raw)
                value_ok = abs(valor - ref_valor) < 0.01

            if text_ok and type_ok and value_ok:
                return {
                    "ref_texto": ref_texto,
                    "doc_soma": self._get_cell_value(ref_row, "DOC. SOMA", self.ref_indices),
                    "desc_soma": self._get_cell_value(ref_row, "DESCRIÇÃO SOMA", self.ref_indices),
                }

        return None

    def _build_target_row(self, source_row: list) -> list:
        """Build base target row."""
        row = [""] * len(self.target_headers)

        data_mov = self._get_cell_value(source_row, "DATA MOV.", self.source_indices)
        desc = self._get_cell_value(source_row, "DESCRIÇÃO", self.source_indices)
        valor = self._get_cell_value(source_row, "IMPORTÂNCIA", self.source_indices)
        tipo = self._get_cell_value(source_row, "TIPO", self.source_indices)
        id_interno = self._get_cell_value(source_row, "ID_INTERNO", self.source_indices)

        self._set_cell_value(row, "DATA MOV.", data_mov, self.target_indices)
        self._set_cell_value(row, "DESCRIÇÃO", self._normalize_text(desc), self.target_indices)
        self._set_cell_value(row, "IMPORTÂNCIA", self._format_number(
            abs(self._parse_amount(valor))
        ), self.target_indices)
        self._set_cell_value(row, "TIPO", tipo, self.target_indices)
        self._set_cell_value(row, "PERÍODO", self._get_month_text(data_mov), self.target_indices)
        self._set_cell_value(row, "PROCESSO", "T_EXTRATO", self.target_indices)
        self._set_cell_value(row, "ID_INTERNO", id_interno, self.target_indices)

        return row

    def _enrich_with_match(self, target_row: list, match: dict) -> list:
        """Add matching data to target row."""
        # Add doc_soma and desc_soma if available
        if match.get("doc_soma"):
            self._set_cell_value(target_row, "DOC. SOMA", match["doc_soma"], self.target_indices)
        if match.get("desc_soma"):
            self._set_cell_value(target_row, "DESCRIÇÃO SOMA", match["desc_soma"], self.target_indices)

        return target_row

    # Helper methods

    def _get_index(self, column_name: str, indices: dict) -> Optional[int]:
        """Get column index."""
        return indices.get(column_name.upper())

    def _get_cell_value(self, row: list, column_name: str, indices: dict) -> str:
        """Get cell value."""
        idx = self._get_index(column_name, indices)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    def _set_cell_value(self, row: list, column_name: str, value: str, indices: dict) -> None:
        """Set cell value."""
        idx = self._get_index(column_name, indices)
        if idx is not None and idx < len(row):
            row[idx] = value

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text."""
        if not text:
            return ""
        text = str(text).replace(" ", "").upper()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    @staticmethod
    def _parse_amount(value: str) -> float:
        """Parse amount."""
        if not value:
            return 0.0
        try:
            return float(str(value).strip().replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _format_number(value: float) -> str:
        """Format number with comma."""
        return f"{value:.2f}".replace(".", ",")

    def _get_month_text(self, data_str: str) -> str:
        """Extract month."""
        if not data_str:
            return ""
        try:
            date_obj = datetime.strptime(str(data_str).strip(), "%d/%m/%Y")
            return self.MESES[date_obj.month - 1]
        except (ValueError, IndexError):
            return ""
