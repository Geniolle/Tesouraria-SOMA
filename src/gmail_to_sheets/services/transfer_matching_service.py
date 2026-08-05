"""
Transfer + Matching Service (Integrated Batch)

Combines transfer and matching in a single optimized pipeline.
Prepares complete CONTAORDEM rows with CONSTANTES data in one batch operation.
"""

import logging
import unicodedata
from datetime import datetime
from typing import Any, Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.services.batch_updater import BatchUpdater
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

        # Cache sheet IDs to avoid extra API calls
        self._sheet_ids_cache: dict[str, int] = {}

        # Sequential state for DESCRIÇÃO SOMA (by date + base description)
        self._seq_state: dict[str, dict[str, Any]] = {}
        self._init_sequential_state()

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

    def _init_sequential_state(self) -> None:
        """Initialize sequential state from existing DESCRIÇÃO SOMA values."""
        try:
            range_name = f"{self.target_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            data_idx = self.target_indices.get("DATA MOV.")
            desc_soma_idx = self.target_indices.get("DESCRIÇÃO SOMA")

            if data_idx is None or desc_soma_idx is None:
                return

            for row in rows:
                if data_idx >= len(row) or desc_soma_idx >= len(row):
                    continue

                data_mov = str(row[data_idx]).strip()
                desc_soma = str(row[desc_soma_idx]).strip()

                if not data_mov or not desc_soma:
                    continue

                # Extract base and sequence number
                # "DÍZIMOS E OFERTAS N003" → base="DÍZIMOS E OFERTAS", num=3
                parts = desc_soma.rsplit(" ", 1)
                if len(parts) == 2 and parts[1].startswith("N"):
                    desc_base = parts[0]
                    try:
                        seq_num = int(parts[1][1:])  # Remove 'N' and convert
                        data_key = data_mov[:5]  # "DD/MM"
                        key = f"{data_key}||{desc_base}"

                        if key not in self._seq_state:
                            self._seq_state[key] = {"max": 0, "base": desc_base}

                        self._seq_state[key]["max"] = max(self._seq_state[key]["max"], seq_num)
                    except (ValueError, IndexError):
                        pass

            logger.info(f"Initialized sequential state with {len(self._seq_state)} entries")

        except Exception as e:
            logger.warning(f"Failed to initialize sequential state: {e}")

    def _load_existing_ids(self) -> dict:
        """Load existing IDs from target with their row numbers."""
        try:
            range_name = f"{self.target_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            id_idx = self.target_indices.get("ID_INTERNO")

            if id_idx is None:
                return {}

            existing = {}
            for i, row in enumerate(rows):
                if id_idx < len(row) and row[id_idx]:
                    id_norm = self._normalize_text(str(row[id_idx]))
                    existing[id_norm] = i + 2  # Row number (1-indexed, +1 for header)

            logger.info(f"Loaded {len(existing)} existing IDs in target sheet")
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
            update_rows = prepared.get("update_rows", {})
            stats = prepared["stats"]

            logger.info(f"Prepared: {len(target_rows)} new rows, "
                       f"{len(update_rows)} updates, "
                       f"{stats['matched']} matched total, "
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

            # Phase 3: Update existing rows with matching data
            if update_rows:
                logger.info(f"Phase 3: Updating {len(update_rows)} existing rows with matching data...")
                updater = BatchUpdater(
                    sheets_client=self.sheets_client,
                    spreadsheet_id=self.spreadsheet_id,
                    sheet_name=self.target_sheet,
                )
                update_result = updater.update_rows(update_rows)
                logger.info(f"Update result: {update_result['updated']} cells updated, {update_result['errors']} errors")

            logger.info(f"Completed: {stats['transferred']} transferred, "
                       f"{stats['already_exists']} updated, "
                       f"{stats['matched']} with matches")

            return stats

        except Exception as e:
            logger.error(f"Process failed: {e}")
            raise

    def _prepare_with_matching(self, source_rows: list[list]) -> dict:
        """
        Prepare all rows with matching in a single pass.
        Handles both new inserts and updates to existing rows.

        Returns:
            Dictionary with target_rows, status_updates, and stats
        """
        target_rows = []
        status_updates = {}
        update_rows = {}  # For updates to existing records
        stats = {
            "transferred": 0,
            "already_exists": 0,
            "updated": 0,
            "empty_id": 0,
            "with_status": 0,
            "matched": 0,
            "no_match": 0,
            "total_processed": 0,
        }

        for idx, source_row in enumerate(source_rows):
            row_number = idx + 2
            stats["total_processed"] += 1

            # Get ID
            id_interno = self._get_cell_value(source_row, "ID_INTERNO", self.source_indices)
            id_normalized = self._normalize_text(id_interno)

            if not id_interno:
                status_updates[row_number] = "Erro: ID vazio"
                stats["empty_id"] += 1
                continue

            # Check status - only process if NOT "Erro" or other error status
            status_idx = self._get_index("STATUS", self.source_indices)
            status_val = ""
            if status_idx is not None and status_idx < len(source_row):
                status_val = str(source_row[status_idx]).strip()

            # Skip if status indicates error (but allow "Transferido" for re-matching)
            if status_val and status_val.startswith("Erro"):
                stats["with_status"] += 1
                continue

            # Try to match with reference data
            try:
                match = self._find_match(source_row)
                if match:
                    stats["matched"] += 1
                    logger.debug(f"Row {row_number}: Match found")
                else:
                    stats["no_match"] += 1
                    logger.debug(f"Row {row_number}: No match - setting DOC.SOMA to ANALISAR")
                    # If no match found, mark DOC.SOMA for manual analysis
                    match = {"doc_soma": "ANALISAR"}

                # Check if already exists in target
                if id_normalized in self.existing_ids:
                    # Prepare update for existing row
                    target_row_num = self.existing_ids[id_normalized]
                    if match:
                        update_rows[target_row_num] = {
                            "PLANO DE CONTA": match.get("plano_conta", ""),
                            "CENTRO DE CUSTO": match.get("centro_custo", ""),
                            "DESCRIÇÃO SOMA": match.get("desc_soma", ""),
                            "TIPO": match.get("tipo", ""),
                            "FORMA DE PAGAMENTO": match.get("forma_pag", ""),
                            "CAIXA": match.get("caixa", ""),
                            "CAIXA SAIDA": match.get("caixa_saida", ""),
                            "DOC. SOMA": match.get("doc_soma", ""),
                        }
                    stats["already_exists"] += 1
                    stats["updated"] += 1
                else:
                    # Prepare new row
                    target_row = self._build_target_row(source_row)
                    if match:
                        target_row = self._enrich_with_match(target_row, match, source_row)

                    target_rows.append(target_row)
                    self.existing_ids[id_normalized] = len(target_rows)  # Track for dedup
                    status_updates[row_number] = "Transferido"
                    stats["transferred"] += 1

            except Exception as e:
                status_updates[row_number] = f"Erro: {str(e)[:40]}"
                logger.error(f"Row {row_number}: {e}")

        # Add update_rows to batch for processing
        return {
            "target_rows": target_rows,
            "status_updates": status_updates,
            "update_rows": update_rows,
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

            # Type matching: strict - both types must match (if both present)
            type_ok = True
            if ref_tipo and tipo:
                type_ok = (tipo == ref_tipo)

            value_ok = True
            if ref_valor_raw and ref_valor_raw.strip():
                ref_valor = self._parse_amount(ref_valor_raw)
                value_ok = abs(valor - ref_valor) < 0.01

            if text_ok and type_ok and value_ok:
                return {
                    "ref_texto": ref_texto,
                    # Conditional field (only if filled in CONSTANTES)
                    "doc_soma": self._get_cell_value(ref_row, "DOC. SOMA", self.ref_indices),
                    # Mandatory fields (copy always)
                    "plano_conta": self._get_cell_value(ref_row, "PLANO DE CONTA", self.ref_indices),
                    "centro_custo": self._get_cell_value(ref_row, "CENTRO DE CUSTO", self.ref_indices),
                    "desc_soma": self._get_cell_value(ref_row, "DESCRIÇÃO SOMA", self.ref_indices),
                    "tipo": self._get_cell_value(ref_row, "TIPO", self.ref_indices),
                    "forma_pag": self._get_cell_value(ref_row, "FORMA DE PAGAMENTO", self.ref_indices),
                    "caixa": self._get_cell_value(ref_row, "CAIXA", self.ref_indices),
                    "caixa_saida": self._get_cell_value(ref_row, "CAIXA SAIDA", self.ref_indices),
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

        # Build a dict of column_name -> value to ensure correct indices
        values_dict = {
            "DATA MOV.": data_mov,
            "DESCRIÇÃO": self._normalize_text(desc),
            "IMPORTÂNCIA": self._format_number(abs(self._parse_amount(valor))),
            "TIPO": tipo,
            "PERÍODO": self._get_month_text(data_mov),
            "PROCESSO": "T_EXTRATO",
            "ID_INTERNO": id_interno,
        }

        # Set all values using explicit column name mapping
        for col_name, col_value in values_dict.items():
            self._set_cell_value(row, col_name, col_value, self.target_indices)

        # Validate row before returning
        logger.debug(f"Built row with {len([v for v in row if v])} non-empty cells out of {len(row)} total")

        return row

    def _generate_sequential_description(self, data_mov: str, desc_soma_base: str) -> str:
        """Generate DESCRIÇÃO SOMA with sequential number by date and base."""
        # Extract date key (DD/MM)
        data_key = data_mov[:5]
        key = f"{data_key}||{desc_soma_base}"

        # Initialize state if needed
        if key not in self._seq_state:
            self._seq_state[key] = {"max": 0, "base": desc_soma_base}

        # Increment and generate
        self._seq_state[key]["max"] += 1
        next_num = self._seq_state[key]["max"]

        return f"{desc_soma_base} N{next_num:03d}"

    def _enrich_with_match(self, target_row: list[Any], match: dict[str, Any], source_row: list[Any] | None = None) -> list[Any]:
        """Add matching data to target row."""
        # Mandatory fields (always copy)
        if match.get("plano_conta"):
            self._set_cell_value(target_row, "PLANO DE CONTA", match["plano_conta"], self.target_indices)
        if match.get("centro_custo"):
            self._set_cell_value(target_row, "CENTRO DE CUSTO", match["centro_custo"], self.target_indices)

        # DESCRIÇÃO SOMA with sequential numbering
        if match.get("desc_soma"):
            data_mov = self._get_cell_value(source_row, "DATA MOV.", self.source_indices) if source_row else ""
            desc_soma_base = match.get("desc_soma")

            if data_mov and desc_soma_base:
                # Generate sequential description
                desc_soma_sequential = self._generate_sequential_description(data_mov, desc_soma_base)
                self._set_cell_value(target_row, "DESCRIÇÃO SOMA", desc_soma_sequential, self.target_indices)
            else:
                self._set_cell_value(target_row, "DESCRIÇÃO SOMA", desc_soma_base, self.target_indices)

        if match.get("tipo"):
            self._set_cell_value(target_row, "TIPO", match["tipo"], self.target_indices)
        if match.get("forma_pag"):
            self._set_cell_value(target_row, "FORMA DE PAGAMENTO", match["forma_pag"], self.target_indices)
        if match.get("caixa"):
            self._set_cell_value(target_row, "CAIXA", match["caixa"], self.target_indices)
        if match.get("caixa_saida"):
            self._set_cell_value(target_row, "CAIXA SAIDA", match["caixa_saida"], self.target_indices)

        # Conditional field (only if filled in CONSTANTES)
        if match.get("doc_soma"):
            self._set_cell_value(target_row, "DOC. SOMA", match["doc_soma"], self.target_indices)

        return target_row

    def _batch_update_existing(self, update_rows: dict) -> None:
        """Update existing rows with matching data."""
        try:
            doc_soma_idx = self.target_indices.get("DOC. SOMA")
            desc_soma_idx = self.target_indices.get("DESCRIÇÃO SOMA")

            if not update_rows or (doc_soma_idx is None and desc_soma_idx is None):
                logger.warning("No valid columns to update")
                return

            requests = []

            for row_num, updates in update_rows.items():
                # Build update requests for each column
                if "DOC. SOMA" in updates and doc_soma_idx is not None:
                    requests.append({
                        "updateCells": {
                            "range": {
                                "sheetId": self._get_sheet_id(self.target_sheet),
                                "rowIndex": row_num - 1,
                                "columnIndex": doc_soma_idx,
                                "endColumnIndex": doc_soma_idx + 1,
                            },
                            "rows": [{
                                "values": [{
                                    "userEnteredValue": {"stringValue": updates["DOC. SOMA"]}
                                }]
                            }],
                            "fields": "userEnteredValue",
                        }
                    })

                if "DESCRIÇÃO SOMA" in updates and desc_soma_idx is not None:
                    requests.append({
                        "updateCells": {
                            "range": {
                                "sheetId": self._get_sheet_id(self.target_sheet),
                                "rowIndex": row_num - 1,
                                "columnIndex": desc_soma_idx,
                                "endColumnIndex": desc_soma_idx + 1,
                            },
                            "rows": [{
                                "values": [{
                                    "userEnteredValue": {"stringValue": updates["DESCRIÇÃO SOMA"]}
                                }]
                            }],
                            "fields": "userEnteredValue",
                        }
                    })

            if requests:
                body = {"requests": requests}
                self.sheets_client.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=body
                ).execute()
                logger.info(f"Updated {len(update_rows)} existing rows")

        except Exception as e:
            logger.error(f"Failed to update existing rows: {e}")
            raise

    def _get_sheet_id(self, sheet_name: str) -> int:
        """Get sheet ID from sheet name (cached)."""
        if sheet_name in self._sheet_ids_cache:
            return self._sheet_ids_cache[sheet_name]

        try:
            result = self.sheets_client.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties"
            ).execute()

            for sheet in result.get("sheets", []):
                if sheet["properties"]["title"] == sheet_name:
                    sheet_id = sheet["properties"]["sheetId"]
                    self._sheet_ids_cache[sheet_name] = sheet_id
                    return sheet_id

            raise ValueError(f"Sheet '{sheet_name}' not found")
        except Exception as e:
            logger.error(f"Failed to get sheet ID: {e}")
            raise

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
        """Set cell value with validation."""
        idx = self._get_index(column_name, indices)

        if idx is None:
            logger.warning(f"Column '{column_name}' not found in indices mapping")
            return

        if idx < 0 or idx >= len(row):
            logger.error(f"Index out of range: column '{column_name}' → idx {idx}, row size {len(row)}")
            return

        row[idx] = str(value) if value else ""
        logger.debug(f"Set row[{idx}] ('{column_name}') = '{str(value)[:50]}'...)")

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
