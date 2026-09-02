"""Orchestrator for transferring validated SAÍDAS rows to CONTAORDEM."""

from __future__ import annotations

import logging

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.entradas.entry_deduplication import (
    EntryDeduplicationService,
)
from src.gmail_to_sheets.services.contaordem_sequence import (
    ContaOrdemSequenceService,
)
from src.gmail_to_sheets.services.pt_format import format_date_ddmmyyyy

from .status_updater import SaidaStatusUpdater
from .transfer_service import SaidaTransferService
from .validator import SaidaValidator

logger = logging.getLogger(__name__)


class SaidasOrchestrator:
    """Execute the SAÍDAS -> CONTAORDEM pipeline."""

    source_sheet = "SAÍDAS"
    target_sheet = "CONTAORDEM"

    def __init__(
        self,
        settings=None,
        sheets_client: SheetsClient | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.sheets_client = sheets_client
        self.spreadsheet_id = self.settings.sheets.spreadsheet_id

    def run(self) -> dict:
        self._authenticate_sheets()
        assert self.sheets_client is not None

        source_headers = self.sheets_client.get_headers(
            self.spreadsheet_id,
            self.source_sheet,
        )
        target_headers = self.sheets_client.get_headers(
            self.spreadsheet_id,
            self.target_sheet,
        )

        validator = SaidaValidator(
            self.sheets_client,
            self.spreadsheet_id,
            headers=source_headers,
        )
        transfer = SaidaTransferService(
            self.sheets_client,
            self.spreadsheet_id,
            source_headers=source_headers,
            target_headers=target_headers,
        )
        dedup = EntryDeduplicationService(
            self.sheets_client,
            self.spreadsheet_id,
            headers=target_headers,
        )
        status = SaidaStatusUpdater(
            self.sheets_client,
            self.spreadsheet_id,
            headers=source_headers,
        )
        sequence = ContaOrdemSequenceService(
            self.sheets_client,
            self.spreadsheet_id,
            target_headers,
            transfer.process_name,
        )

        result = self.sheets_client.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.sheets_client.get_data_range(
                self.spreadsheet_id,
                self.source_sheet,
            ),
        ).execute()
        rows = result.get("values", [])

        valid = 0
        transferred = 0
        duplicates = 0
        failed = 0
        transferred_rows: list[int] = []
        duplicate_rows: list[int] = []

        for row_number, row in enumerate(rows, start=2):
            is_valid, _ = validator.is_valid_entry(row, row_number)
            if not is_valid:
                continue

            valid += 1
            data = validator.get_field(row, "DATA") or ""
            valor = validator.get_field(row, "VALOR DA COMPRA") or ""
            descricao = validator.get_field(
                row,
                "DESCRIÇÃO DA COMPRA",
            ) or ""
            id_interno = validator.get_field(row, "ID_INTERNO")

            if dedup.is_duplicate(
                data,
                valor,
                descricao,
                id_interno=id_interno,
            ):
                # Already in CONTAORDEM: do not append again, just flag the
                # source row so it stops being reprocessed every tick.
                duplicates += 1
                duplicate_rows.append(row_number)
                continue

            try:
                day = format_date_ddmmyyyy(data) or (data or "")
                sequence_number = sequence.next_for(day)
                target_row = transfer.build_target_row(row, sequence_number)
                if not transfer.append(target_row):
                    failed += 1
                    continue

                transferred += 1
                transferred_rows.append(row_number)
                dedup.register_new_entry(
                    data,
                    valor,
                    descricao,
                    id_interno=id_interno,
                )
            except Exception:
                failed += 1
                logger.exception(
                    "Failed to transfer SAÍDAS row %s",
                    row_number,
                )

        update_result = status.mark_batch_as_sent(transferred_rows)
        duplicate_result = status.mark_batch_as_duplicate(duplicate_rows)
        sort_result = self.sheets_client.ensure_contaordem_sorted(
            self.spreadsheet_id
        )
        if sort_result.get("sorted"):
            logger.info("CONTAORDEM sorted by DATA MOV. descending")

        summary = {
            "valid": valid,
            "transferred": transferred,
            "duplicates": duplicates,
            "duplicates_marked": duplicate_result["updated"],
            "failed": failed,
            "status_updated": update_result["updated"],
            "status_failed": update_result["failed"],
            "duplicate_mark_failed": duplicate_result["failed"],
        }

        logger.info(
            "SAÍDAS completed valid=%s transferred=%s duplicates=%s "
            "duplicates_marked=%s failed=%s status_updated=%s",
            valid,
            transferred,
            duplicates,
            duplicate_result["updated"],
            failed,
            update_result["updated"],
        )
        return summary

    def _authenticate_sheets(self) -> None:
        if self.sheets_client is not None:
            return

        self.sheets_client = SheetsClient(
            service_account_path=str(
                self.settings.sheets.service_account_path
            )
        )


def run_saidas_process() -> dict:
    """Manual entrypoint for the SAÍDAS process."""
    return SaidasOrchestrator().run()
