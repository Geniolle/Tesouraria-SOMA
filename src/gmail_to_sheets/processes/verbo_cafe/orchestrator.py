"""Orchestrator for the Verbo Café process (sales + supplier payments).

Runs two phases against a spreadsheet that is separate from the main treasury
spreadsheet:

1. ``VENDAS``     - ``VC_VENDAS``  -> CONTAORDEM as ``Entrada``
2. ``PAGAMENTOS`` - ``Financeiro`` -> CONTAORDEM as ``Saída``

Each phase: read source, validate, deduplicate against CONTAORDEM, append the
mapped row with a per-day ``DESCRIÇÃO SOMA`` sequence, then flip the source
``STATUS DA TESOURARIA`` to ``CONCLUÍDO``. CONTAORDEM is sorted by
``DATA MOV.`` descending at the end.
"""

from __future__ import annotations

import logging

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.entradas.entry_deduplication import (
    EntryDeduplicationService,
)

from ._format import format_date_ddmmyyyy
from .config import TARGET_SHEET, VerboCafePhase, resolve_phases
from .daily_sequence import DailySequenceService
from .status_updater import VerboCafeStatusUpdater
from .transfer_service import VerboCafeTransferService
from .validator import VerboCafeValidator

logger = logging.getLogger(__name__)


class VerboCafeOrchestrator:
    """Execute both Verbo Café phases end to end."""

    target_sheet = TARGET_SHEET

    def __init__(
        self,
        settings=None,
        sheets_client: SheetsClient | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.sheets_client = sheets_client
        self.target_spreadsheet_id = self.settings.sheets.spreadsheet_id
        self.source_spreadsheet_id = (
            self.settings.verbo_cafe.source_spreadsheet_id
        )

    def run(self) -> dict:
        self._authenticate_sheets()
        assert self.sheets_client is not None

        summary: dict = {"transferred": 0}
        for phase in resolve_phases(self.settings):
            phase_summary = self._run_phase(phase)
            summary[phase.key] = phase_summary
            summary["transferred"] += phase_summary["transferred"]

        sort_result = self.sheets_client.ensure_contaordem_sorted(
            self.target_spreadsheet_id
        )
        if sort_result.get("sorted"):
            logger.info("CONTAORDEM sorted by DATA MOV. descending")

        logger.info(
            "Verbo Café completed transferred=%s (vendas=%s pagamentos=%s)",
            summary["transferred"],
            summary["vendas"]["transferred"],
            summary["pagamentos"]["transferred"],
        )
        return summary

    def _run_phase(self, phase: VerboCafePhase) -> dict:
        assert self.sheets_client is not None
        client = self.sheets_client

        source_headers = client.get_headers(
            self.source_spreadsheet_id,
            phase.source_sheet,
        )
        target_headers = client.get_headers(
            self.target_spreadsheet_id,
            self.target_sheet,
        )

        validator = VerboCafeValidator(phase, source_headers)
        dedup = EntryDeduplicationService(
            client,
            self.target_spreadsheet_id,
            headers=target_headers,
        )
        sequence = DailySequenceService(
            client,
            self.target_spreadsheet_id,
            target_headers,
            phase.processo_tag,
        )
        transfer = VerboCafeTransferService(
            client,
            self.target_spreadsheet_id,
            source_headers=source_headers,
            target_headers=target_headers,
            phase=phase,
        )
        status = VerboCafeStatusUpdater(
            client,
            self.source_spreadsheet_id,
            source_headers,
            phase,
        )

        result = client.service.spreadsheets().values().get(
            spreadsheetId=self.source_spreadsheet_id,
            range=client.get_data_range(
                self.source_spreadsheet_id,
                phase.source_sheet,
            ),
        ).execute()
        rows = result.get("values", [])

        valid = 0
        transferred = 0
        duplicates = 0
        failed = 0
        transferred_rows: list[int] = []

        for row_number, row in enumerate(rows, start=2):
            is_valid, _ = validator.is_valid_entry(row, row_number)
            if not is_valid:
                continue
            valid += 1

            data_mov = format_date_ddmmyyyy(
                validator.get_field(row, phase.data_field)
            ) or ""
            valor = validator.get_field(row, phase.amount_field) or ""
            descricao = validator.build_descricao(row)
            id_interno = validator.get_field(row, phase.id_field)

            if dedup.is_duplicate(
                data_mov,
                valor,
                descricao,
                id_interno=id_interno,
            ):
                duplicates += 1
                continue

            try:
                sequence_number = sequence.next_for(data_mov)
                target_row = transfer.build_target_row(row, sequence_number)
                if not transfer.append(target_row):
                    failed += 1
                    continue
                transferred += 1
                transferred_rows.append(row_number)
                dedup.register_new_entry(
                    data_mov,
                    valor,
                    descricao,
                    id_interno=id_interno,
                )
            except Exception:  # noqa: BLE001
                failed += 1
                logger.exception(
                    "Failed to transfer %s row %s",
                    phase.source_sheet,
                    row_number,
                )

        update_result = status.mark_batch_as_concluido(transferred_rows)

        logger.info(
            "Verbo Café %s: valid=%s transferred=%s duplicates=%s failed=%s "
            "status_updated=%s",
            phase.key,
            valid,
            transferred,
            duplicates,
            failed,
            update_result["updated"],
        )
        return {
            "valid": valid,
            "transferred": transferred,
            "duplicates": duplicates,
            "failed": failed,
            "status_updated": update_result["updated"],
            "status_failed": update_result["failed"],
        }

    def _authenticate_sheets(self) -> None:
        if self.sheets_client is not None:
            return
        # Standalone runs may point at a dedicated service account for the
        # Verbo Café spreadsheet; scheduled runs reuse the shared client.
        sa_path = (
            self.settings.verbo_cafe.service_account_path
            or self.settings.sheets.service_account_path
        )
        self.sheets_client = SheetsClient(service_account_path=str(sa_path))


def run_verbo_cafe_process() -> dict:
    """Manual entrypoint for the Verbo Café process."""
    return VerboCafeOrchestrator().run()
