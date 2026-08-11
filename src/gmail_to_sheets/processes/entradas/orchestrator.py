"""
Entradas Process Orchestrator

Coordinates the complete pipeline for transferring entries from
DÍZIMOS/OFERTAS to CONTAORDEM.

Pipeline:
1. Validate entries (TIPO, DOC.SOMA, FINANCE, VALOR, DATA)
2. Deduplicate against CONTAORDEM (data+valor+descrição)
3. Transfer to CONTAORDEM with mapped fields
4. Update FINANCE = "Transferido" in DÍZIMOS/OFERTAS
5. Sort CONTAORDEM by DATA MOV. (descending)
"""

import logging

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.entradas.entry_validator import EntryValidator
from src.gmail_to_sheets.processes.entradas.entry_deduplication import (
    EntryDeduplicationService,
)
from src.gmail_to_sheets.processes.entradas.entry_transfer_service import (
    EntryTransferService,
)
from src.gmail_to_sheets.processes.entradas.entry_status_updater import (
    EntryStatusUpdater,
)

logger = logging.getLogger(__name__)


class EntradasOrchestrator:
    """Main orchestrator for Entradas process."""

    def __init__(self):
        """Initialize orchestrator."""
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.sheets_client: SheetsClient | None = None
        self.spreadsheet_id = self.settings.sheets.spreadsheet_id

    def run(self) -> None:
        """Execute complete Entradas pipeline."""
        try:
            logger.info("=" * 80)
            logger.info("Starting Entradas process pipeline")
            logger.info("=" * 80)

            # Phase 1: Authenticate Sheets
            self._authenticate_sheets()

            # Phase 2: Load and validate entries
            entries = self._load_and_validate_entries()
            if not entries:
                logger.warning("No valid entries found for transfer")
                return

            logger.info(f"Found {len(entries['valid'])} valid entries")

            # Phase 3: Deduplicate
            deduped_entries = self._deduplicate_entries(entries["valid"])
            if not deduped_entries:
                logger.warning("No entries after deduplication")
                return

            logger.info(f"After deduplication: {len(deduped_entries)} entries")

            # Phase 4: Transfer to CONTAORDEM
            transfer_result = self._transfer_to_contaordem(deduped_entries)

            # Phase 5: Update FINANCE status
            update_result = self._update_status(transfer_result["transferred_rows"])

            # Phase 6: Sort CONTAORDEM
            self._sort_contaordem()

            logger.info("=" * 80)
            logger.info("Entradas process completed successfully!")
            logger.info(f"  - Total entries processed: {len(entries['valid'])}")
            logger.info(f"  - Invalid entries: {len(entries['invalid'])}")
            logger.info(f"  - Transferred: {transfer_result['transferred']}")
            logger.info(f"  - Duplicates: {transfer_result['duplicates']}")
            logger.info(f"  - Status updated: {update_result['updated']}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise

    def _authenticate_sheets(self) -> None:
        """Authenticate with Google Sheets API."""
        try:
            logger.info("[1/6] Authenticating with Google Sheets...")
            self.sheets_client = SheetsClient(
                service_account_path=str(self.settings.sheets.service_account_path)
            )
            logger.info("      Sheets authenticated")
        except Exception as e:
            logger.error(f"Sheets authentication failed: {e}")
            raise

    def _load_and_validate_entries(self) -> dict:
        """Load entries from DÍZIMOS/OFERTAS and validate them."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("[2/6] Loading and validating entries from DÍZIMOS/OFERTAS...")

            validator = EntryValidator(self.sheets_client, self.spreadsheet_id)

            # Load data
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=self.sheets_client.get_data_range(self.spreadsheet_id, "DÍZIMOS/OFERTAS"),
            ).execute()

            rows = result.get("values", [])
            logger.info(f"      Loaded {len(rows)} rows")

            valid_entries = []
            invalid_entries = []

            for row_num, row in enumerate(rows, start=2):
                is_valid, error = validator.is_valid_entry(row, row_num)

                if is_valid:
                    valid_entries.append({
                        "row_number": row_num,
                        "row_data": row
                    })
                else:
                    invalid_entries.append({
                        "row_number": row_num,
                        "error": error
                    })
                    logger.debug(f"Row {row_num} invalid: {error}")

            logger.info(f"      Valid: {len(valid_entries)}, Invalid: {len(invalid_entries)}")

            return {
                "valid": valid_entries,
                "invalid": invalid_entries
            }

        except Exception as e:
            logger.error(f"Failed to load/validate entries: {e}")
            raise

    def _deduplicate_entries(self, valid_entries: list) -> list:
        """Deduplicate entries against CONTAORDEM."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("[3/6] Deduplicating entries...")

            dedup_service = EntryDeduplicationService(
                self.sheets_client, self.spreadsheet_id
            )

            deduped = []

            for entry in valid_entries:
                row = entry["row_data"]
                row_num = entry["row_number"]

                # Extract key fields for deduplication
                # Column indices match: DATA=3, VALOR=7, NÚMERO DOCUMENTO=6
                data_idx = 3  # DATA (0-indexed)
                valor_idx = 7  # VALOR
                numero_doc_idx = 6  # NÚMERO DOCUMENTO

                if data_idx < len(row) and valor_idx < len(row):
                    data = str(row[data_idx]).strip() if row[data_idx] else ""
                    valor = str(row[valor_idx]).strip() if row[valor_idx] else ""
                    numero_doc = str(row[numero_doc_idx]).strip() if numero_doc_idx < len(row) and row[numero_doc_idx] else ""

                    # Build description
                    if numero_doc:
                        descricao = f"{numero_doc} - DÍZIMOS E OFERTAS (CULTO)"
                    else:
                        descricao = "DÍZIMOS E OFERTAS (CULTO)"

                    # Check duplicate
                    if dedup_service.is_duplicate(data, valor, descricao):
                        logger.debug(f"Row {row_num}: Duplicate (skipped)")
                        continue

                    # Register in dedup cache
                    dedup_service.register_new_entry(data, valor, descricao)
                    deduped.append(entry)

            logger.info(f"      After deduplication: {len(deduped)} entries")
            return deduped

        except Exception as e:
            logger.error(f"Deduplication failed: {e}")
            raise

    def _transfer_to_contaordem(self, entries: list) -> dict:
        """Transfer entries to CONTAORDEM."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("[4/6] Transferring to CONTAORDEM...")

            transfer_service = EntryTransferService(
                self.sheets_client, self.spreadsheet_id
            )

            transferred = 0
            duplicates = 0
            transferred_rows = []

            for entry in entries:
                row = entry["row_data"]
                row_num = entry["row_number"]

                try:
                    # Extract número documento
                    numero_doc_idx = 6
                    numero_doc = str(row[numero_doc_idx]).strip() if numero_doc_idx < len(row) and row[numero_doc_idx] else ""

                    # Build target row
                    target_row = transfer_service.build_target_row(row, numero_doc)

                    # Append to CONTAORDEM
                    if transfer_service.append_row_to_target(target_row):
                        transferred += 1
                        transferred_rows.append(row_num)
                        logger.debug(f"Row {row_num}: Transferred successfully")
                    else:
                        logger.warning(f"Row {row_num}: Failed to append")

                except Exception as e:
                    logger.error(f"Row {row_num}: Transfer error: {e}")
                    duplicates += 1

            logger.info(f"      Transferred: {transferred}")
            return {
                "transferred": transferred,
                "duplicates": duplicates,
                "transferred_rows": transferred_rows
            }

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            raise

    def _update_status(self, transferred_rows: list) -> dict:
        """Update FINANCE status in DÍZIMOS/OFERTAS for transferred rows."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("[5/6] Updating status in DÍZIMOS/OFERTAS...")

            updater = EntryStatusUpdater(self.sheets_client, self.spreadsheet_id)

            result = updater.mark_batch_as_transferred(transferred_rows)

            logger.info(f"      Updated: {result['updated']}, Failed: {result['failed']}")
            return result

        except Exception as e:
            logger.error(f"Status update failed: {e}")
            raise

    def _sort_contaordem(self) -> None:
        """Sort CONTAORDEM by DATA MOV. descending."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("[6/6] Sorting CONTAORDEM by DATA MOV....")

            transfer_service = EntryTransferService(
                self.sheets_client, self.spreadsheet_id
            )
            transfer_service.sort_by_date()

            logger.info("      Sort completed")

        except Exception as e:
            logger.error(f"Sort failed: {e}")
            # Don't raise - sorting is not critical


def run_entradas_process():
    """Entry point for Entradas process."""
    orchestrator = EntradasOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    run_entradas_process()
