"""
Direct tests for Orchestrator.run() fail-safe pipeline.

All tests call orchestrator.run() directly to validate:
- Correct execution order of pipeline phases
- Error propagation stops remaining phases
- Proper pass-through of IDs and data
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.orchestrator import Orchestrator
from src.gmail_to_sheets.services.batch_updater import BatchUpdater


def _create_orchestrator():
    """Factory: Create fully-controlled Orchestrator."""
    orchestrator = Orchestrator.__new__(Orchestrator)

    # Settings
    orchestrator.settings = Mock()
    orchestrator.settings.gmail.account_email = "test@example.com"
    orchestrator.settings.gmail.search_query = "test"
    orchestrator.settings.gmail.backup_label_name = "Backup"
    orchestrator.settings.batch_size = 10
    orchestrator.settings.sheets.spreadsheet_id = "test_sheet"
    orchestrator.settings.sheets.sheet_name = "T_EXTRATO"
    orchestrator.settings.log_file = "/tmp/test.log"
    orchestrator.settings.log_level = "INFO"

    # Clients
    orchestrator.gmail_client = Mock()
    orchestrator.sheets_client = Mock()
    orchestrator.sheets_writer = Mock()

    return orchestrator


class TestBatchUpdaterDirect:
    """Test BatchUpdater.update_rows() directly."""

    def test_batch_updater_success(self):
        """Test BatchUpdater succeeds with valid updates."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=["COL1", "COL2", "COL3"])
        mock_sheets.service = Mock()

        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(
                update=Mock(return_value=Mock(
                    execute=Mock(return_value={"updatedCells": 1})
                ))
            ))
        ))

        updater = BatchUpdater(mock_sheets, "test_spreadsheet", "TEST_SHEET")
        result = updater.update_rows({1: {"COL1": "value"}})

        assert result["updated"] == 1
        assert result["errors"] == 0

    def test_batch_updater_propagates_error(self):
        """Test BatchUpdater propagates API errors."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=["COL1", "COL2"])
        mock_sheets.service = Mock()

        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(
                update=Mock(side_effect=RuntimeError("API error"))
            ))
        ))

        updater = BatchUpdater(mock_sheets, "test_spreadsheet", "TEST_SHEET")

        with pytest.raises(RuntimeError, match="Batch update failed"):
            updater.update_rows({1: {"COL1": "value"}})


class TestOrchestratorRunFailSafe:
    """Direct tests of orchestrator.run() fail-safe behavior."""

    def test_run_success_calls_all_steps_in_order_with_matching(self):
        """Test run() calls all steps in correct order with matching enabled."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = True
        orchestrator.settings.cash_balance.update_enabled = True
        orchestrator.settings.archive_after_process = True

        call_order = []

        # Setup method mocks with side_effect to track order
        orchestrator._authenticate_gmail = Mock(
            side_effect=lambda: call_order.append("authenticate_gmail")
        )
        orchestrator._authenticate_sheets = Mock(
            side_effect=lambda: call_order.append("authenticate_sheets")
        )
        orchestrator._search_messages = Mock(
            side_effect=lambda: (
                call_order.append("search"),
                ["msg_old", "msg_new"]
            )[1]
        )
        orchestrator._select_latest_message = Mock(
            side_effect=lambda ids: (
                call_order.append("select_latest"),
                "msg_new"
            )[1]
        )
        orchestrator._download_and_parse = Mock(
            side_effect=lambda msg_id: (
                call_order.append("parse"),
                Mock(
                    transactions=[Mock(), Mock()],
                    header=Mock(saldo_abertura=Decimal("2000.00")),
                    footer=Mock(saldo_fecho=Decimal("2148.04")),
                    total_transactions=2
                )
            )[1]
        )
        orchestrator._validate_mt940_reconciliation = Mock(
            side_effect=lambda mt940: call_order.append("reconcile")
        )
        orchestrator._write_to_sheets = Mock(
            side_effect=lambda mt940, dedup: (
                call_order.append("write"),
                {
                    "written": 2,
                    "skipped": 0,
                    "total": 2,
                    "written_ids": ["EXT0000000001", "EXT0000000002"]
                }
            )[1]
        )
        orchestrator._transfer_with_matching = Mock(
            side_effect=lambda ids: (
                call_order.append("transfer_matching"),
                {
                    "transferred": 2,
                    "already_exists": 0,
                    "matched": 2,
                    "no_match": 0
                }
            )[1]
        )
        orchestrator._update_cash_balance = Mock(
            side_effect=lambda balance: (
                call_order.append("balance"),
                {
                    "target_cell": "C2",
                    "written_value": "2148,04",
                    "verified_value": "2148.04"
                }
            )[1]
        )
        orchestrator._archive_email = Mock(
            side_effect=lambda msg_id: call_order.append("archive")
        )

        # Call run() directly
        orchestrator.run()

        # Validate order
        expected_order = [
            "authenticate_gmail",
            "authenticate_sheets",
            "search",
            "select_latest",
            "parse",
            "reconcile",
            "write",
            "transfer_matching",
            "balance",
            "archive",
        ]
        assert call_order == expected_order

        # Validate method calls
        orchestrator._transfer_with_matching.assert_called_once_with(
            ["EXT0000000001", "EXT0000000002"]
        )
        orchestrator._update_cash_balance.assert_called_once_with(
            Decimal("2148.04")
        )
        orchestrator._archive_email.assert_called_once_with("msg_new")

    def test_run_uses_transfer_service_when_matching_disabled(self):
        """Test run() uses TransferService when matching disabled."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = False
        orchestrator.settings.archive_after_process = True

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 0, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            return_value={"transferred": 0, "already_exists": 0}
        )
        orchestrator._transfer_with_matching = Mock()
        orchestrator._update_cash_balance = Mock()
        orchestrator._archive_email = Mock()

        orchestrator.run()

        # Verify correct transfer service used
        orchestrator._transfer_to_contaordem.assert_called_once_with([])
        orchestrator._transfer_with_matching.assert_not_called()

    def test_run_write_failure_stops_remaining_steps(self):
        """Test run() stops after write failure."""
        orchestrator = _create_orchestrator()

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            side_effect=RuntimeError("T_EXTRATO write failed")
        )
        orchestrator._transfer_to_contaordem = Mock()
        orchestrator._transfer_with_matching = Mock()
        orchestrator._update_cash_balance = Mock()
        orchestrator._archive_email = Mock()

        with pytest.raises(RuntimeError, match="T_EXTRATO write failed"):
            orchestrator.run()

        # Verify transfer and archive not called
        orchestrator._transfer_to_contaordem.assert_not_called()
        orchestrator._transfer_with_matching.assert_not_called()
        orchestrator._update_cash_balance.assert_not_called()
        orchestrator._archive_email.assert_not_called()

    def test_run_transfer_failure_stops_balance_and_archive(self):
        """Test run() stops at transfer failure."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = True
        orchestrator.settings.archive_after_process = True

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 0, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            side_effect=RuntimeError("CONTAORDEM transfer failed")
        )
        orchestrator._update_cash_balance = Mock()
        orchestrator._archive_email = Mock()

        with pytest.raises(RuntimeError, match="CONTAORDEM transfer failed"):
            orchestrator.run()

        # Verify balance and archive not called
        orchestrator._update_cash_balance.assert_not_called()
        orchestrator._archive_email.assert_not_called()

    def test_run_balance_failure_stops_archive(self):
        """Test run() stops at balance failure."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = True
        orchestrator.settings.archive_after_process = True

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 0, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            return_value={"transferred": 0, "already_exists": 0}
        )
        orchestrator._update_cash_balance = Mock(
            side_effect=RuntimeError("Cash balance update failed")
        )
        orchestrator._archive_email = Mock()

        with pytest.raises(RuntimeError, match="Cash balance update failed"):
            orchestrator.run()

        # Verify archive not called
        orchestrator._archive_email.assert_not_called()

    def test_run_archive_failure_propagates_and_does_not_log_success(self):
        """Test run() propagates archive failure without logging success."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = False
        orchestrator.settings.archive_after_process = True

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 0, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            return_value={"transferred": 0, "already_exists": 0}
        )
        orchestrator._archive_email = Mock(
            side_effect=RuntimeError("Archive failed")
        )

        with pytest.raises(RuntimeError, match="Archive failed"):
            orchestrator.run()

    def test_run_zero_written_ids_transfers_empty_list(self):
        """Test run() transfers empty list when written_ids empty."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = False
        orchestrator.settings.archive_after_process = True

        transfer_ids_received = None

        def capture_transfer_ids(source_ids=None):
            nonlocal transfer_ids_received
            transfer_ids_received = source_ids
            return {"transferred": 0, "already_exists": 0}

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 8, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            side_effect=capture_transfer_ids
        )
        orchestrator._archive_email = Mock()

        orchestrator.run()

        # Verify transfer received empty list, not None
        assert transfer_ids_received == []
        orchestrator._archive_email.assert_called_once()

    def test_run_does_not_archive_when_archive_setting_disabled(self):
        """Test run() skips archive when setting disabled."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = False
        orchestrator.settings.archive_after_process = False

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 0, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            return_value={"transferred": 0, "already_exists": 0}
        )
        orchestrator._archive_email = Mock()

        orchestrator.run()

        # Archive should not be called
        orchestrator._archive_email.assert_not_called()

    def test_run_does_not_update_balance_when_balance_setting_disabled(self):
        """Test run() skips balance when setting disabled."""
        orchestrator = _create_orchestrator()
        orchestrator.settings.enable_matching = False
        orchestrator.settings.cash_balance.update_enabled = False
        orchestrator.settings.archive_after_process = True

        orchestrator._authenticate_gmail = Mock()
        orchestrator._authenticate_sheets = Mock()
        orchestrator._search_messages = Mock(return_value=["msg_1"])
        orchestrator._select_latest_message = Mock(return_value="msg_1")
        orchestrator._download_and_parse = Mock(
            return_value=Mock(
                transactions=[Mock()],
                header=Mock(saldo_abertura=Decimal("0")),
                footer=Mock(saldo_fecho=Decimal("0")),
                total_transactions=1
            )
        )
        orchestrator._validate_mt940_reconciliation = Mock()
        orchestrator._write_to_sheets = Mock(
            return_value={"written": 0, "skipped": 0, "written_ids": []}
        )
        orchestrator._transfer_to_contaordem = Mock(
            return_value={"transferred": 0, "already_exists": 0}
        )
        orchestrator._update_cash_balance = Mock()
        orchestrator._archive_email = Mock()

        orchestrator.run()

        # Balance should not be called
        orchestrator._update_cash_balance.assert_not_called()
        # Archive should be called after transfer
        orchestrator._archive_email.assert_called_once()
