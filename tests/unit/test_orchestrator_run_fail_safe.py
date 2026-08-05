"""
Real tests for fail-safe orchestrator components.

Tests validate:
- BatchUpdater error propagation
- Orchestrator._select_latest_message() behavior
"""

from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.orchestrator import Orchestrator
from src.gmail_to_sheets.services.batch_updater import BatchUpdater


class TestBatchUpdaterDirect:
    """Test BatchUpdater.update_rows() directly."""

    def test_batch_updater_success(self):
        """Test BatchUpdater succeeds with valid updates."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=["COL1", "COL2", "COL3"])
        mock_sheets.service = Mock()

        # Mock successful update
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

        # Mock update failure
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(
                update=Mock(side_effect=RuntimeError("API error"))
            ))
        ))

        updater = BatchUpdater(mock_sheets, "test_spreadsheet", "TEST_SHEET")

        with pytest.raises(RuntimeError, match="Batch update failed"):
            updater.update_rows({1: {"COL1": "value"}})


class TestOrchestratorSelectLatestMessage:
    """Test Orchestrator._select_latest_message() real behavior."""

    def test_select_latest_message_with_multiple_messages(self):
        """Test _select_latest_message selects by timestamp."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        mock_gmail = Mock()

        # Return messages with different internalDate values
        mock_gmail.get_message = Mock(side_effect=[
            {"id": "msg_1", "internalDate": "1625097600000"},  # oldest
            {"id": "msg_2", "internalDate": "1625097610000"},  # newest
            {"id": "msg_3", "internalDate": "1625097605000"},  # middle
        ])

        orchestrator.gmail_client = mock_gmail

        # Call with multiple IDs
        selected = orchestrator._select_latest_message(["msg_1", "msg_2", "msg_3"])

        # Should select msg_2 (highest internalDate)
        assert selected == "msg_2"

    def test_select_latest_message_single_message(self):
        """Test _select_latest_message with single message."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        mock_gmail = Mock()
        mock_gmail.get_message = Mock(
            return_value={"id": "msg_1", "internalDate": "1625097610000"}
        )

        orchestrator.gmail_client = mock_gmail
        selected = orchestrator._select_latest_message(["msg_1"])

        assert selected == "msg_1"

    def test_select_latest_message_empty_list_raises(self):
        """Test _select_latest_message raises on empty list."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.gmail_client = Mock()

        with pytest.raises(ValueError, match="No messages to select"):
            orchestrator._select_latest_message([])
