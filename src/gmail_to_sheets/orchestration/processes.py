"""Managed-process adapters for the central orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from src.gmail_to_sheets.clients.sheets_projection import read_projected_rows
from src.gmail_to_sheets.orchestrator import Orchestrator as ExtratoOrchestrator
from src.gmail_to_sheets.processes.conciliacao.lookup_service import LookupService
from src.gmail_to_sheets.processes.conciliacao.orchestrator import (
    ConciliationOrchestrator,
)
from src.gmail_to_sheets.processes.conciliacao.validator import ConciliationValidator
from src.gmail_to_sheets.processes.entradas.entry_deduplication import (
    EntryDeduplicationService,
)
from src.gmail_to_sheets.processes.entradas.entry_validator import EntryValidator
from src.gmail_to_sheets.processes.entradas.orchestrator import EntradasOrchestrator
from src.gmail_to_sheets.processes.faturas_email.orchestrator import (
    FaturasEmailOrchestrator,
)
from src.gmail_to_sheets.processes.saidas.orchestrator import SaidasOrchestrator
from src.gmail_to_sheets.processes.saidas.validator import SaidaValidator
from src.gmail_to_sheets.processes.verbo_cafe.config import resolve_phases
from src.gmail_to_sheets.processes.verbo_cafe.orchestrator import (
    VerboCafeOrchestrator,
)
from src.gmail_to_sheets.processes.verbo_cafe.validator import VerboCafeValidator

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
    def _build_success(
        process_name: str,
        processed: int,
        started_at: float,
    ) -> ProcessResult:
        return ProcessResult(
            process_name=process_name,
            status=ProcessStatus.SUCCESS,
            processed=processed,
            duration_seconds=perf_counter() - started_at,
        )

    @staticmethod
    def _build_failed(
        process_name: str,
        error: Exception,
        started_at: float,
    ) -> ProcessResult:
        return ProcessResult(
            process_name=process_name,
            status=ProcessStatus.FAILED,
            processed=0,
            duration_seconds=perf_counter() - started_at,
            error=str(error),
        )

    @staticmethod
    def _row_value(
        row: list,
        column_indices: dict[str, int],
        field_name: str,
    ) -> str:
        index = column_indices.get(field_name.upper().strip())
        if index is None or index >= len(row) or row[index] is None:
            return ""
        return str(row[index]).strip()


class ExtratoProcess(_BaseManagedProcess):
    """Managed wrapper around the Extrato process."""

    name = "Extrato"
    priority = 10

    def __init__(self, context: ProcessContext) -> None:
        super().__init__(context)
        self._pending_message_ids: list[str] = []

    def check_pending(self) -> PendingResult:
        """Check Gmail cheaply without downloading messages or attachments."""
        gmail_client = self.context.get_gmail_client()
        message_ids = gmail_client.search_messages(
            query=self.context.settings.gmail.search_query,
            max_results=1,
        )
        self._pending_message_ids = message_ids
        if not message_ids:
            return PendingResult(
                has_work=False,
                count=0,
                reason="No matching Gmail messages",
            )
        return PendingResult(
            has_work=True,
            count=1,
            reason="Matching Gmail message found",
        )

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
            logger.error(
                "Extrato process failed during managed execution: %s",
                error,
                exc_info=True,
            )
            return self._build_failed(self.name, error, started_at)


class DizimosOfertasProcess(_BaseManagedProcess):
    """Managed DÍZIMOS/OFERTAS -> CONTAORDEM transfer process."""

    name = "DizimosOfertas"
    priority = 20
    source_sheet = "DÍZIMOS/OFERTAS"
    required_fields = (
        "DATA",
        "TIPO",
        "DOC. SOMA",
        "NÚMERO DOCUMENTO",
        "VALOR",
        "FINANCE",
        "ID_INTERNO",
    )

    def __init__(self, context: ProcessContext) -> None:
        super().__init__(context)
        self._pending_entries: list[_PendingEntry] = []

    def check_pending(self) -> PendingResult:
        """Find the first valid non-duplicate DÍZIMOS/OFERTAS row."""
        sheets_client = self.context.get_sheets_client()
        spreadsheet_id = self.context.settings.sheets.spreadsheet_id
        headers = self.context.get_sheet_headers(self.source_sheet)
        validator = EntryValidator(
            sheets_client,
            spreadsheet_id,
            headers=headers,
        )

        rows = read_projected_rows(
            sheets_client,
            spreadsheet_id,
            self.source_sheet,
            validator.column_indices,
            self.required_fields,
        )

        dedup: EntryDeduplicationService | None = None
        self._pending_entries = []

        for row_number, row in rows:
            is_valid, _ = validator.is_valid_entry(row, row_number)
            if not is_valid:
                continue

            data = self._row_value(
                row,
                validator.column_indices,
                "DATA",
            )
            valor = self._row_value(
                row,
                validator.column_indices,
                "VALOR",
            )
            numero_documento = self._row_value(
                row,
                validator.column_indices,
                "NÚMERO DOCUMENTO",
            )
            id_interno = self._row_value(
                row,
                validator.column_indices,
                "ID_INTERNO",
            )
            descricao = (
                f"{numero_documento} - DÍZIMOS E OFERTAS (CULTO)"
                if numero_documento
                else "DÍZIMOS E OFERTAS (CULTO)"
            )

            if dedup is None:
                dedup = EntryDeduplicationService(
                    sheets_client,
                    spreadsheet_id,
                    headers=self.context.get_sheet_headers("CONTAORDEM"),
                )

            if dedup.is_duplicate(
                data,
                valor,
                descricao,
                id_interno=id_interno,
            ):
                continue

            self._pending_entries = [
                _PendingEntry(
                    row_number=row_number,
                    row_data=row,
                )
            ]
            return PendingResult(
                has_work=True,
                count=1,
                reason="DÍZIMOS/OFERTAS row ready for transfer",
            )

        return PendingResult(
            has_work=False,
            count=0,
            reason="No DÍZIMOS/OFERTAS rows ready for transfer",
        )

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
            logger.error(
                "DizimosOfertas failed during managed execution: %s",
                error,
                exc_info=True,
            )
            return self._build_failed(self.name, error, started_at)


class SaidasProcess(_BaseManagedProcess):
    """Managed SAÍDAS -> CONTAORDEM transfer process."""

    name = "Saidas"
    priority = 30
    source_sheet = "SAÍDAS"
    required_fields = (
        "ID_INTERNO",
        "DATA",
        "TIPO",
        "DOC. SOMA",
        "VALOR DA COMPRA",
        "DESCRIÇÃO DA COMPRA",
        "STATUS DA TESOURARIA",
        "FINANCE",
    )

    def __init__(self, context: ProcessContext) -> None:
        super().__init__(context)
        self._pending_entries: list[_PendingEntry] = []

    def check_pending(self) -> PendingResult:
        """Find the first SAÍDAS row that still needs action.

        A row with an empty ``FINANCE`` that passes validation is always
        work (transfer, or first ``duplicado`` flag). A row already
        flagged ``duplicado`` is work only when its CONTAORDEM match is
        gone (stale flag that must now be transferred); that recheck runs
        only when there is no cheaper pending row, to keep the common
        "nothing to do" tick from probing CONTAORDEM.
        """
        sheets_client = self.context.get_sheets_client()
        spreadsheet_id = self.context.settings.sheets.spreadsheet_id
        headers = self.context.get_sheet_headers(self.source_sheet)
        validator = SaidaValidator(
            sheets_client,
            spreadsheet_id,
            headers=headers,
        )

        rows = read_projected_rows(
            sheets_client,
            spreadsheet_id,
            self.source_sheet,
            validator.column_indices,
            self.required_fields,
        )

        self._pending_entries = []
        flagged: list[tuple[int, list[str]]] = []

        for row_number, row in rows:
            is_valid, _ = validator.is_valid_entry(row, row_number)
            if not is_valid:
                continue

            finance_state = (
                validator.get_field(row, "FINANCE") or ""
            ).strip().casefold()
            if finance_state == "duplicado":
                flagged.append((row_number, row))
                continue

            self._pending_entries = [
                _PendingEntry(row_number=row_number, row_data=row)
            ]
            return PendingResult(
                has_work=True,
                count=1,
                reason="SAÍDAS row ready for transfer",
            )

        if flagged:
            dedup = EntryDeduplicationService(
                sheets_client,
                spreadsheet_id,
                headers=self.context.get_sheet_headers("CONTAORDEM"),
            )
            for row_number, row in flagged:
                data = validator.get_field(row, "DATA") or ""
                valor = validator.get_field(row, "VALOR DA COMPRA") or ""
                descricao = validator.get_field(
                    row,
                    "DESCRIÇÃO DA COMPRA",
                ) or ""
                id_interno = validator.get_field(row, "ID_INTERNO")
                if not dedup.is_duplicate(
                    data,
                    valor,
                    descricao,
                    id_interno=id_interno,
                ):
                    self._pending_entries = [
                        _PendingEntry(row_number=row_number, row_data=row)
                    ]
                    return PendingResult(
                        has_work=True,
                        count=1,
                        reason=(
                            "SAÍDAS 'duplicado' row no longer in CONTAORDEM"
                        ),
                    )

        return PendingResult(
            has_work=False,
            count=0,
            reason="No SAÍDAS rows ready for transfer",
        )

    def run(self) -> ProcessResult:
        started_at = perf_counter()
        try:
            orchestrator = SaidasOrchestrator(
                settings=self.context.settings,
                sheets_client=self.context.get_sheets_client(),
            )
            summary = orchestrator.run() or {}
            processed = int(summary.get("transferred", 0))
            return self._build_success(self.name, processed, started_at)
        except Exception as error:
            logger.error(
                "Saidas failed during managed execution: %s",
                error,
                exc_info=True,
            )
            return self._build_failed(self.name, error, started_at)


class ConciliacaoProcess(_BaseManagedProcess):
    """Managed wrapper around the T_EXTRATO reconciliation process."""

    name = "Conciliacao"
    priority = 40
    source_required_fields = ("DOC. SOMA", "ID_INTERNO")

    def __init__(
        self,
        context: ProcessContext,
        source_sheet: str = "T_EXTRATO",
    ) -> None:
        super().__init__(context)
        self.source_sheet = source_sheet
        self._pending_candidates: list[dict[str, str]] = []

    def check_pending(self) -> PendingResult:
        """Check only for reconciliation rows that are actionable now."""
        sheets_client = self.context.get_sheets_client()
        spreadsheet_id = self.context.settings.sheets.spreadsheet_id
        source_headers = self.context.get_sheet_headers(self.source_sheet)
        validator = ConciliationValidator(
            sheets_client,
            spreadsheet_id,
            self.source_sheet,
            headers=source_headers,
        )

        rows = read_projected_rows(
            sheets_client,
            spreadsheet_id,
            self.source_sheet,
            validator.column_indices,
            self.source_required_fields,
        )

        candidates: list[dict[str, str]] = []
        for row_number, row in rows:
            is_candidate, _ = validator.is_candidate_for_reconciliation(
                row,
                row_number,
            )
            if not is_candidate:
                continue

            id_interno = validator.extract_search_key(row)
            if not id_interno:
                continue

            candidates.append(
                {
                    "row_number": str(row_number),
                    "id_interno": id_interno,
                }
            )

        if not candidates:
            self._pending_candidates = []
            return PendingResult(
                has_work=False,
                count=0,
                reason="No reconciliation candidates",
            )

        contaordem_headers = self.context.get_sheet_headers("CONTAORDEM")
        lookup_service = LookupService(
            sheets_client,
            spreadsheet_id,
            headers=contaordem_headers,
        )
        lookup_service.load_contaordem_data(
            required_ids={item["id_interno"] for item in candidates}
        )

        actionable: list[dict[str, str]] = []
        for candidate in candidates:
            lookup = lookup_service.lookup_doc_soma(
                candidate["id_interno"]
            )
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
            return PendingResult(
                has_work=False,
                count=0,
                reason="No actionable reconciliation rows",
            )

        return PendingResult(
            has_work=True,
            count=len(actionable),
            reason="Actionable reconciliation rows found",
        )

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
            logger.error(
                "Conciliacao process failed during managed execution: %s",
                error,
                exc_info=True,
            )
            return self._build_failed(self.name, error, started_at)


class VerboCafeProcess(_BaseManagedProcess):
    """Managed Verbo Café process: VC_VENDAS + Financeiro -> CONTAORDEM."""

    name = "VerboCafe"
    priority = 35
    target_sheet = "CONTAORDEM"

    def check_pending(self) -> PendingResult:
        """Find the first actionable non-duplicate row across both phases."""
        sheets_client = self.context.get_sheets_client()
        source_id = self.context.settings.verbo_cafe.source_spreadsheet_id
        target_id = self.context.settings.sheets.spreadsheet_id
        dedup: EntryDeduplicationService | None = None

        for phase in resolve_phases(self.context.settings):
            source_headers = self.context.get_sheet_headers(
                phase.source_sheet,
                source_id,
            )
            validator = VerboCafeValidator(phase, source_headers)

            rows = read_projected_rows(
                sheets_client,
                source_id,
                phase.source_sheet,
                validator.column_indices,
                phase.required_headers,
            )

            for row_number, row in rows:
                is_valid, _ = validator.is_valid_entry(row, row_number)
                if not is_valid:
                    continue

                data = self._row_value(
                    row,
                    validator.column_indices,
                    phase.data_field,
                )
                valor = self._row_value(
                    row,
                    validator.column_indices,
                    phase.amount_field,
                )
                id_interno = self._row_value(
                    row,
                    validator.column_indices,
                    phase.id_field,
                )
                descricao = validator.build_descricao(row)

                if dedup is None:
                    dedup = EntryDeduplicationService(
                        sheets_client,
                        target_id,
                        headers=self.context.get_sheet_headers(
                            self.target_sheet
                        ),
                    )

                if dedup.is_duplicate(
                    data,
                    valor,
                    descricao,
                    id_interno=id_interno,
                ):
                    continue

                return PendingResult(
                    has_work=True,
                    count=1,
                    reason=f"Verbo Café: {phase.key} row ready for transfer",
                )

        return PendingResult(
            has_work=False,
            count=0,
            reason="No Verbo Café rows ready for transfer",
        )

    def run(self) -> ProcessResult:
        started_at = perf_counter()
        try:
            orchestrator = VerboCafeOrchestrator(
                settings=self.context.settings,
                sheets_client=self.context.get_sheets_client(),
            )
            summary = orchestrator.run() or {}
            processed = int(summary.get("transferred", 0))
            return self._build_success(self.name, processed, started_at)
        except Exception as error:
            logger.error(
                "VerboCafe failed during managed execution: %s",
                error,
                exc_info=True,
            )
            return self._build_failed(self.name, error, started_at)


class FaturasEmailProcess(_BaseManagedProcess):
    """Managed process: save email attachments to a Google Drive folder."""

    name = "FaturasEmail"
    priority = 50

    def check_pending(self) -> PendingResult:
        """Cheap Gmail probe across every configured route."""
        cfg = self.context.settings.faturas_email
        if not cfg.routes:
            return PendingResult(
                has_work=False,
                count=0,
                reason="No Faturas Email routes configured",
            )

        gmail_client = self.context.get_gmail_client()
        for route in cfg.routes:
            message_ids = gmail_client.search_messages(
                query=route.gmail_query(),
                max_results=1,
            )
            if message_ids:
                return PendingResult(
                    has_work=True,
                    count=1,
                    reason=f"Matching email for {route.sender}",
                )

        return PendingResult(
            has_work=False,
            count=0,
            reason="No matching Faturas emails",
        )

    def run(self) -> ProcessResult:
        started_at = perf_counter()
        try:
            orchestrator = FaturasEmailOrchestrator(
                settings=self.context.settings,
                gmail_client=self.context.get_gmail_client(),
                drive_client=self.context.get_drive_client(),
            )
            summary = orchestrator.run() or {}
            processed = int(summary.get("processed", 0))
            return self._build_success(self.name, processed, started_at)
        except Exception as error:
            logger.error(
                "FaturasEmail failed during managed execution: %s",
                error,
                exc_info=True,
            )
            return self._build_failed(self.name, error, started_at)


EntradasProcess = DizimosOfertasProcess
