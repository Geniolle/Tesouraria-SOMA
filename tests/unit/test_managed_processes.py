from pathlib import Path
from unittest.mock import Mock, patch

from src.gmail_to_sheets.orchestration.models import ProcessContext
from src.gmail_to_sheets.orchestration.processes import (
    ConciliacaoProcess,
    EntradasProcess,
    ExtratoProcess,
)


def _make_settings():
    settings = Mock()
    settings.log_file = "logs/test.log"
    settings.log_level = "INFO"
    settings.gmail = Mock()
    settings.gmail.search_query = "in:inbox has:attachment"
    settings.gmail.client_secrets_path = Path("/tmp/secret.json")
    settings.gmail.credentials_path = Path("/tmp/token.json")
    settings.sheets = Mock()
    settings.sheets.spreadsheet_id = "sheet-123"
    settings.sheets.service_account_path = Path("/tmp/service.json")
    settings.sheets.sheet_name = "T_EXTRATO"
    return settings


def _make_sheet_client(rows_by_range):
    client = Mock()
    client.get_data_range.side_effect = lambda spreadsheet_id, sheet_name: f"'{sheet_name}'!A2:Z99999"
    client.get_headers.side_effect = lambda spreadsheet_id, sheet_name: rows_by_range["headers"].get(sheet_name, [])

    def values_get(spreadsheetId, range):
        sheet_name = str(range).split("!", 1)[0].replace("'", "")
        payload = rows_by_range["values"].get(sheet_name, {"values": []})
        return Mock(execute=Mock(return_value=payload))

    client.service = Mock()
    client.service.spreadsheets.return_value.values.return_value.get.side_effect = values_get
    client.service.spreadsheets.return_value.values.return_value.append = Mock()
    client.service.spreadsheets.return_value.values.return_value.update = Mock()
    client.append_rows = Mock()
    client.update_cell = Mock()
    return client


class TestExtratoProcess:
    @patch("src.gmail_to_sheets.orchestration.processes.ExtratoOrchestrator")
    def test_check_pending_is_read_only_and_uses_max_results_one(self, mock_orch_cls):
        settings = _make_settings()
        gmail_client = Mock()
        gmail_client.search_messages.return_value = ["msg-1"]
        gmail_client.get_message = Mock()
        gmail_client.archive_message = Mock()
        gmail_client.add_label = Mock()
        context = ProcessContext(settings=settings, gmail_client=gmail_client, sheets_client=Mock())

        process = ExtratoProcess(context)
        pending = process.check_pending()

        assert pending.has_work is True
        gmail_client.search_messages.assert_called_once_with(
            query="in:inbox has:attachment",
            max_results=1,
        )
        gmail_client.get_message.assert_not_called()
        gmail_client.archive_message.assert_not_called()
        gmail_client.add_label.assert_not_called()

    def test_check_pending_reports_no_work_when_no_message(self):
        settings = _make_settings()
        gmail_client = Mock()
        gmail_client.search_messages.return_value = []
        context = ProcessContext(settings=settings, gmail_client=gmail_client, sheets_client=Mock())

        process = ExtratoProcess(context)
        pending = process.check_pending()

        assert pending.has_work is False
        assert pending.count == 0


class TestEntradasProcess:
    @patch("src.gmail_to_sheets.orchestration.processes.EntryValidator")
    def test_check_pending_uses_entry_validator(self, mock_validator_cls):
        settings = _make_settings()
        rows_by_range = {
            "headers": {
                "DÍZIMOS/OFERTAS": ["DATA", "TIPO", "DOC. SOMA", "FINANCE", "VALOR"],
            },
            "values": {
                "DÍZIMOS/OFERTAS": {
                    "values": [
                        ["01/08/2026", "DÍZIMOS/OFERTAS", "DOC1", "", "10.00"],
                        ["02/08/2026", "DÍZIMOS/OFERTAS", "", "", "5.00"],
                    ]
                }
            },
        }
        sheet_client = _make_sheet_client(rows_by_range)
        validator = Mock()
        validator.is_valid_entry.side_effect = [(True, None), (False, "DOC.SOMA vazio")]
        mock_validator_cls.return_value = validator
        context = ProcessContext(settings=settings, sheets_client=sheet_client, gmail_client=Mock())

        process = EntradasProcess(context)
        pending = process.check_pending()

        assert pending.has_work is True
        assert pending.count == 1
        mock_validator_cls.assert_called_once()
        validator.is_valid_entry.assert_any_call(["01/08/2026", "DÍZIMOS/OFERTAS", "DOC1", "", "10.00"], 2)
        sheet_client.append_rows.assert_not_called()
        sheet_client.update_cell.assert_not_called()

    @patch("src.gmail_to_sheets.orchestration.processes.EntryValidator")
    def test_check_pending_skips_when_no_valid_entries(self, mock_validator_cls):
        settings = _make_settings()
        rows_by_range = {
            "headers": {
                "DÍZIMOS/OFERTAS": ["DATA", "TIPO", "DOC. SOMA", "FINANCE", "VALOR"],
            },
            "values": {
                "DÍZIMOS/OFERTAS": {
                    "values": [
                        ["01/08/2026", "DÍZIMOS/OFERTAS", "", "", "10.00"],
                    ]
                }
            },
        }
        sheet_client = _make_sheet_client(rows_by_range)
        validator = Mock()
        validator.is_valid_entry.return_value = (False, "DOC.SOMA vazio")
        mock_validator_cls.return_value = validator
        context = ProcessContext(settings=settings, sheets_client=sheet_client, gmail_client=Mock())

        process = EntradasProcess(context)
        pending = process.check_pending()

        assert pending.has_work is False
        assert pending.count == 0
        sheet_client.append_rows.assert_not_called()
        sheet_client.update_cell.assert_not_called()


class TestConciliacaoProcess:
    def test_check_pending_skips_when_no_doc_soma_in_contaordem(self):
        settings = _make_settings()
        rows_by_range = {
            "headers": {
                "T_EXTRATO": ["DOC. SOMA", "ID_INTERNO"],
                "CONTAORDEM": ["ID_INTERNO", "DOC. SOMA"],
            },
            "values": {
                "T_EXTRATO": {
                    "values": [
                        ["", "EXT0000000001"],
                    ]
                },
                "CONTAORDEM": {
                    "values": [
                        ["EXT0000000001", ""],
                    ]
                },
            },
        }
        sheet_client = _make_sheet_client(rows_by_range)
        context = ProcessContext(settings=settings, sheets_client=sheet_client, gmail_client=Mock())

        process = ConciliacaoProcess(context)
        pending = process.check_pending()

        assert pending.has_work is False
        assert pending.count == 0
        sheet_client.append_rows.assert_not_called()
        sheet_client.update_cell.assert_not_called()

    def test_check_pending_runs_when_doc_soma_is_available(self):
        settings = _make_settings()
        rows_by_range = {
            "headers": {
                "T_EXTRATO": ["DOC. SOMA", "ID_INTERNO"],
                "CONTAORDEM": ["ID_INTERNO", "DOC. SOMA"],
            },
            "values": {
                "T_EXTRATO": {
                    "values": [
                        ["", "EXT0000000001"],
                    ]
                },
                "CONTAORDEM": {
                    "values": [
                        ["EXT0000000001", "DOC-1"],
                    ]
                },
            },
        }
        sheet_client = _make_sheet_client(rows_by_range)
        context = ProcessContext(settings=settings, sheets_client=sheet_client, gmail_client=Mock())

        process = ConciliacaoProcess(context)
        pending = process.check_pending()

        assert pending.has_work is True
        assert pending.count == 1
        sheet_client.append_rows.assert_not_called()
        sheet_client.update_cell.assert_not_called()
