"""
Update existing rows in CONTAORDEM with matching data from CONSTANTES.
"""

import logging
import unicodedata
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


class MatchingUpdater:
    """Update existing rows with matching data."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        target_sheet: str = "CONTAORDEM",
        reference_sheet: str = "CONSTANTES",
    ):
        """Initialize matching updater."""
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.target_sheet = target_sheet
        self.reference_sheet = reference_sheet

        # Load headers
        self.target_headers = self._load_headers(target_sheet)
        self.ref_headers = self._load_headers(reference_sheet)

        self.target_indices = self._map_columns(self.target_headers)
        self.ref_indices = self._map_columns(self.ref_headers)

        # Load reference data
        self.ref_data = self._load_reference_data()

    def _load_headers(self, sheet_name: str) -> list[str]:
        """Load headers from sheet."""
        return self.sheets_client.get_headers(self.spreadsheet_id, sheet_name)

    def _map_columns(self, headers: list[str]) -> dict[str, int]:
        """Map column names to indices."""
        return {str(h).strip().upper(): idx for idx, h in enumerate(headers)}

    def _load_reference_data(self) -> list[list]:
        """Load reference data."""
        try:
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.reference_sheet}!A2:Z99999",
            ).execute()
            rows = result.get("values", [])
            logger.info(f"Loaded {len(rows)} reference rows")
            return rows
        except Exception as e:
            logger.error(f"Failed to load reference data: {e}")
            raise

    def update_matching_for_existing(self) -> dict:
        """Find and update existing rows with matching data."""
        stats = {
            "total_rows": 0,
            "updated": 0,
            "matched": 0,
            "no_match": 0,
            "errors": 0,
        }

        try:
            # Load target data
            range_name = f"{self.target_sheet}!A2:Z99999"
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            logger.info(f"Processing {len(rows)} target rows...")

            # Collect updates
            updates: dict[int, dict[str, str]] = {}

            for row_idx, row in enumerate(rows):
                row_number = row_idx + 2  # Account for header and 1-based indexing
                stats["total_rows"] += 1

                # Check if DOC.SOMA already has value
                doc_soma_idx = self.target_indices.get("DOC.SOMA")
                if doc_soma_idx is not None and doc_soma_idx < len(row):
                    if str(row[doc_soma_idx]).strip():
                        continue  # Already has value

                # Get description
                desc_idx = self.target_indices.get("DESCRIÇÃO")
                if desc_idx is None or desc_idx >= len(row):
                    continue

                desc = str(row[desc_idx]).strip()
                if not desc:
                    continue

                # Try to match
                match = self._find_match(desc)
                if match:
                    if row_number not in updates:
                        updates[row_number] = {}

                    if match.get("doc_soma"):
                        updates[row_number]["DOC.SOMA"] = match["doc_soma"]
                    if match.get("desc_soma"):
                        updates[row_number]["DESCRIÇÃO SOMA"] = match["desc_soma"]

                    stats["matched"] += 1
                else:
                    stats["no_match"] += 1

            logger.info(f"Found {len(updates)} rows to update")

            # Batch write updates
            if updates:
                self._batch_update_rows(updates)
                stats["updated"] = len(updates)

            return stats

        except Exception as e:
            logger.error(f"Update failed: {e}", exc_info=True)
            stats["errors"] = 1
            raise

    def _find_match(self, description: str) -> Optional[dict]:
        """Find matching reference row."""
        desc_norm = self._normalize_text(description)

        for ref_row in self.ref_data:
            if not ref_row:
                continue

            texto_idx = self.ref_indices.get("TEXTO")
            if texto_idx is None or texto_idx >= len(ref_row):
                continue

            ref_texto = str(ref_row[texto_idx]).strip()
            if not ref_texto:
                continue

            ref_texto_norm = self._normalize_text(ref_texto)

            # Check if text matches
            if (desc_norm in ref_texto_norm) or (ref_texto_norm in desc_norm):
                doc_soma_idx = self.ref_indices.get("DOC. SOMA")
                desc_soma_idx = self.ref_indices.get("DESCRIÇÃO SOMA")

                doc_soma = str(ref_row[doc_soma_idx]).strip() if doc_soma_idx < len(ref_row) else ""
                desc_soma = str(ref_row[desc_soma_idx]).strip() if desc_soma_idx < len(ref_row) else ""

                return {
                    "doc_soma": doc_soma,
                    "desc_soma": desc_soma,
                }

        return None

    def _batch_update_rows(self, updates: dict) -> None:
        """Batch update rows using appendCells."""
        try:
            # Build requests
            requests = []

            for row_num, cols in updates.items():
                for col_name, value in cols.items():
                    col_idx = self.target_indices.get(col_name)
                    if col_idx is None:
                        continue

                    requests.append({
                        "appendCells": {
                            "sheetId": self._get_sheet_id(),
                            "rows": [{
                                "values": [{
                                    "userEnteredValue": {"stringValue": value}
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
                logger.info(f"Batch update completed: {len(updates)} rows")

        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            raise

    def _get_sheet_id(self) -> int:
        """Get target sheet ID."""
        try:
            result = self.sheets_client.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties"
            ).execute()

            for sheet in result.get("sheets", []):
                if sheet["properties"]["title"] == self.target_sheet:
                    return sheet["properties"]["sheetId"]

            raise ValueError(f"Sheet '{self.target_sheet}' not found")
        except Exception as e:
            logger.error(f"Failed to get sheet ID: {e}")
            raise

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text."""
        if not text:
            return ""
        text = str(text).replace(" ", "").upper()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
