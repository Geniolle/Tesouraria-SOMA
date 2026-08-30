from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.orchestration.central import CentralOrchestrator
from src.gmail_to_sheets.orchestration.health import HealthStore
from src.gmail_to_sheets.orchestration.models import (
    PendingResult,
    ProcessResult,
    ProcessStatus,
)
from src.gmail_to_sheets.orchestration.registry import ProcessRegistry


def _client_without_auth() -> SheetsClient:
    client = SheetsClient.__new__(SheetsClient)
    client.service = Mock()
    client._dirty_sheets = set()
    return client


def test_sort_contaordem_uses_data_mov_descending():
    client = _client_without_auth()
    client.get_headers = Mock(
        return_value=["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA"]
    )
    client.get_sheet_id = Mock(return_value=123)
    client.get_last_row = Mock(return_value=50)
    execute = Mock(return_value={})
    client.service.spreadsheets.return_value.batchUpdate.return_value.execute = (
        execute
    )

    client.mark_sheet_dirty("CONTAORDEM")
    result = client.ensure_contaordem_sorted("spreadsheet-1")

    assert result["sorted"] is True
    assert client.is_sheet_dirty("CONTAORDEM") is False

    call = client.service.spreadsheets.return_value.batchUpdate.call_args
    assert call.kwargs["spreadsheetId"] == "spreadsheet-1"

    request = call.kwargs["body"]["requests"][0]["sortRange"]
    assert request["range"] == {
        "sheetId": 123,
        "startRowIndex": 1,
        "endRowIndex": 50,
        "startColumnIndex": 0,
        "endColumnIndex": 3,
    }
    assert request["sortSpecs"] == [
        {
            "dimensionIndex": 0,
            "sortOrder": "DESCENDING",
        }
    ]


def test_clean_contaordem_does_not_call_google_sort():
    client = _client_without_auth()

    result = client.ensure_contaordem_sorted("spreadsheet-1")

    assert result["sorted"] is False
    client.service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_sort_requires_data_mov_column():
    client = _client_without_auth()
    client.get_headers = Mock(return_value=["DESCRIÇÃO", "IMPORTÂNCIA"])
    client.get_sheet_id = Mock(return_value=123)
    client.get_last_row = Mock(return_value=10)
    client.mark_sheet_dirty("CONTAORDEM")

    with pytest.raises(RuntimeError, match="DATA MOV"):
        client.ensure_contaordem_sorted("spreadsheet-1")

    assert client.is_sheet_dirty("CONTAORDEM") is True


def test_append_to_contaordem_marks_sheet_dirty():
    client = _client_without_auth()
    execute = Mock(
        return_value={"updates": {"updatedRows": 1}}
    )
    client.service.spreadsheets.return_value.values.return_value.append.return_value.execute = (
        execute
    )

    client.append_rows(
        "spreadsheet-1",
        "CONTAORDEM",
        [["30/08/2026", "TESTE"]],
    )

    assert client.is_sheet_dirty("CONTAORDEM") is True


def test_update_cell_in_contaordem_marks_sheet_dirty():
    client = _client_without_auth()
    execute = Mock(return_value={"updatedCells": 1})
    client.service.spreadsheets.return_value.values.return_value.update.return_value.execute = (
        execute
    )

    client.update_cell(
        "spreadsheet-1",
        "CONTAORDEM",
        10,
        5,
        "DOC-1",
    )

    assert client.is_sheet_dirty("CONTAORDEM") is True


class _MutatingProcess:
    name = "Teste"
    priority = 10

    def check_pending(self):
        return PendingResult(
            has_work=True,
            count=1,
            reason="work",
        )

    def run(self):
        return ProcessResult(
            process_name=self.name,
            status=ProcessStatus.SUCCESS,
            processed=1,
        )


def _settings():
    settings = Mock()
    settings.log_file = "logs/test.log"
    settings.log_level = "INFO"
    settings.sheets = Mock()
    settings.sheets.spreadsheet_id = "spreadsheet-1"
    return settings


def test_central_orchestrator_enforces_dirty_contaordem(tmp_path):
    process = _MutatingProcess()
    orchestrator = CentralOrchestrator(
        settings=_settings(),
        registry=ProcessRegistry([process]),
        health_store=HealthStore(tmp_path / "health.json"),
    )
    sheets_client = Mock()
    sheets_client.is_sheet_dirty.return_value = True
    sheets_client.ensure_contaordem_sorted.return_value = {
        "sorted": True,
    }
    orchestrator.context.sheets_client = sheets_client

    summary = orchestrator.run_tick()

    assert summary.results[0].status == ProcessStatus.SUCCESS
    sheets_client.ensure_contaordem_sorted.assert_called_once_with(
        "spreadsheet-1"
    )


def test_sort_failure_marks_process_failed(tmp_path):
    process = _MutatingProcess()
    orchestrator = CentralOrchestrator(
        settings=_settings(),
        registry=ProcessRegistry([process]),
        health_store=HealthStore(tmp_path / "health.json"),
    )
    sheets_client = Mock()
    sheets_client.is_sheet_dirty.return_value = True
    sheets_client.ensure_contaordem_sorted.side_effect = RuntimeError(
        "sort unavailable"
    )
    orchestrator.context.sheets_client = sheets_client

    summary = orchestrator.run_tick()

    result = summary.results[0]
    assert result.status == ProcessStatus.FAILED
    assert "CONTAORDEM sort failed" in (result.error or "")
