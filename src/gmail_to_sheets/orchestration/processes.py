"""Managed-process adapters for the central orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from src.gmail_to_sheets.orchestrator import Orchestrator as ExtratoOrchestrator
from src.gmail_to_sheets.processes.conciliacao.lookup_service import LookupService
from src.gmail_to_sheets.processes.conciliacao.orchestrator import (
    ConciliationOrchestrator,
)
from src.gmail_to_sheets.processes.conciliacao.validator import ConciliationValidator
from src.gmail_to_sheets.processes.entradas.entry_validator import EntryValidator
from src.gmail_to_sheets.processes.entradas.orchestrator import EntradasOrchestrator

from .models import PendingResult, ProcessContext, ProcessResult, ProcessStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PendingEntry:
    row_number: int
    row_data: list[str]


class _BaseManagedProcess:
    """Shared helpers for managed processes."""

    name: str
    priority: int

    def __init__(self, context: ProcessContext) -> None:
        self.context = context

    @staticmethod
    def _build_success(process_name: str, processed: int, started_at: float) -> ProcessResult:
        return ProcessResult(
            process_name=process_name,
            status=ProcessStatus.SUCCESS,
            processed=processed,
            duration_seconds=perf_counter() - started_at,
        )

    @staticmethod
    def _build_skipped(process_name: str, reason: str, started_at: float) -> ProcessResult:
        return ProcessResult(
            process_name=process_name,
            status=ProcessStatus.SKIPPED,
            processed=0,
            duration_seconds=perf_counter() - started_at,
            error=reason,
        )

    @staticmethod
    def _build_failed(process_name: str, error: Exception, started_at: float) -> ProcessResult:
        return ProcessResult(
            process_name=process_name,
            status=ProcessStatus.FAILED,
            processed=0,
            duration_seconds=perf_counter() - started_at,
            error=str(error),
        )


class ExtratoProcess(_BaseManagedProcess):
    """Managed wrapper around the Extrato process."""

    name = "Extrato"
    priority = 10

    def __init__(self, context: ProcessContext) -> None:
        super().__init__(context)
        self._pending_message_ids: list[str] = []

    def check_pending(self) -> PendingResult:
        gmail_client = self.context.get_gmail_client()
        message_ids = gmail_client.search_messages(
            query=self.context.settings.gmail.search_query,
            max_results=1,
        )
        self._pending_message_ids = message_ids
        if not message_ids:
            return PendingResult(has_work=False, count=0, reason="No matching Gmail messages")
        return PendingResult(has_work=True, count=len(message_ids), reason="Matching Gmail message found")

    def run(self) -> ProcessResult:
        started_at = perf_counter()
        try:
            orchestrator = ExtratoOrchestrator(
                settings=self.context.settings,
                gmail_client=self.context.get_gmail_client(),
                sheets_client=self.context.get_sheets_client(),
            )
            summary = orchestrator.run() or {}
            processed = int(summary.get("written", 0))
            return self._build_success(self.name, processed, started_at)
        except Exception as error:
            logger.error("Extrato process failed during managed execution: %s", error, exc_info=True)
            return self._build_failed(self.name, error, started_at)


class EntradasProcess(_BaseManagedProcess):
    """Managed wrapper around the Entradas process."""

    name = "Entradas"
    priority = 20

    def __init__(self, context: ProcessContext) -> None:
        super().__init__(context)
        self._pending_entries: list[_PendingEntry] = []

    def check_pending(self) -> PendingResult:
        sheets_client = self.context.get_sheets_client()
        validator = EntryValidator(sheets_client, self.context.settings.sheets.spreadsheet_id)
        result = sheets_client.service.spreadsheets().values().get(
            spreadsheetId=self.context.settings.sheets.spreadsheet_id,
            range=sheets_client.get_data_range(
                self.context.settings.sheets.spreadsheet_id, "DÍZIMOS/OFERTAS"
            ),
        ).execute()

        rows = result.get("values", [])
        pending_rows: list[_PendingEntry] = []
        for row_number, row in enumerate(rows, start=2):
            is_valid, _ = validator.is_valid_entry(row, row_number)
            if is_valid:
                pending_rows.append(_PendingEntry(row_number=row_number, row_data=row))

        self._pending_entries = pending_rows
        if not pending_rows:
            return PendingResult(has_work=False, count=0, reason="No valid entries pending")
        return PendingResult(has_work=True, count=len(pending_rows), reason="Valid entries pending")

    def run(self) -> ProcessResult:
        started_at = perf_counter()
        try:
            orchestrator = EntradasOrchestrator(
                settings=self.context.settings,
                sheets_client=self.context.get_sheets_client(),
            )
            summary = orchestrator.run() or {}
            processed = int(summary.get("transferred", 0))
            return self._build_success(self.name, processed, started_at)
        except Exception as error:
            logger.error("Entradas process failed during managed execution: %s", error, exc_info=True)
            return self._build_failed(self.name, error, started_at)


class ConciliacaoProcess(_BaseManagedProcess):
    """Managed wrapper around the Conciliacao process."""

    name = "Conciliacao"
    priority = 30

    def __init__(self, context: ProcessContext, source_sheet: str = "T_EXTRATO") -> None:
        super().__init__(context)
        self.source_sheet = source_sheet
        self._pending_candidates: list[dict[str, str]] = []

    def check_pending(self) -> PendingResult:
        sheets_client = self.context.get_sheets_client()
        spreadsheet_id = self.context.settings.sheets.spreadsheet_id
        validator = ConciliationValidator(sheets_client, spreadsheet_id, self.source_sheet)
        result = sheets_client.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheets_client.get_data_range(spreadsheet_id, self.source_sheet),
        ).execute()

        rows = result.get("values", [])
        candidates: list[dict[str, str]] = []
        for row_number, row in enumerate(rows, start=2):
            is_candidate, _ = validator.is_candidate_for_reconciliation(row, row_number)
            if not is_candidate:
                continue
            id_interno = validator.extract_search_key(row)
            if not id_interno:
                continue
            candidates.append({"row_number": str(row_number), "id_interno": id_interno})

        if not candidates:
            self._pending_candidates = []
            return PendingResult(has_work=False, count=0, reason="No reconciliation candidates")

        lookup_service = LookupService(sheets_client, spreadsheet_id)
        lookup_service.load_contaordem_data()

        actionable: list[dict[str, str]] = []
        for candidate in candidates:
            lookup = lookup_service.lookup_doc_soma(candidate["id_interno"])
            if lookup.get("found") and lookup.get("doc_soma"):
                actionable.append(
                    {
                        "row_number": candidate["row_number"],
                        "id_interno": candidate["id_interno"],
                        "doc_soma": str(lookup["doc_soma"]),
                    }
                )

        self._pending_candidates = actionable
        if not actionable:
            return PendingResult(has_work=False, count=0, reason="No actionable reconciliation rows")
        return PendingResult(has_work=True, count=len(actionable), reason="Actionable reconciliation rows found")

    def run(self) -> ProcessResult:
        started_at = perf_counter()
        try:
            orchestrator = ConciliationOrchestrator(
                source_sheet=self.source_sheet,
                settings=self.context.settings,
                sheets_client=self.context.get_sheets_client(),
            )
            summary = orchestrator.run() or {}
            processed = int(summary.get("reconciled", 0))
            return self._build_success(self.name, processed, started_at)
        except Exception as error:
            logger.error("Conciliacao process failed during managed execution: %s", error, exc_info=True)
            return self._build_failed(self.name, error, started_at)
