"""
Security hardening tests for Orchestrator.

Tests validate:
- Latest message selection by internalDate
- Deduplication registration
- Error propagation in transfers
- Error propagation in archiving
- Integrated pipeline scenarios
"""

from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.orchestrator import Orchestrator


class TestSelectLatestMessage:
    """Test email selection by internalDate."""

    def test_select_single_message(self):
        """Test selection with single message."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        mock_gmail = Mock()
        orchestrator.gmail_client = mock_gmail

        message_ids = ["msg_123"]
        mock_gmail.get_message.return_value = {"id": "msg_123", "internalDate": "1625097600000"}

        selected = orchestrator._select_latest_message(message_ids)
        assert selected == "msg_123"

    def test_select_latest_from_unordered_messages(self):
        """Test selection from messages in wrong order."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        mock_gmail = Mock()
        orchestrator.gmail_client = mock_gmail

        message_ids = ["msg_1", "msg_2", "msg_3"]
        # Return them out of order - msg_2 is actually newest
        mock_gmail.get_message.side_effect = [
            {"id": "msg_1", "internalDate": "1625097600000"},  # oldest
            {"id": "msg_2", "internalDate": "1625097610000"},  # newest
            {"id": "msg_3", "internalDate": "1625097600500"},  # middle
        ]

        selected = orchestrator._select_latest_message(message_ids)
        assert selected == "msg_2"

    def test_select_skips_messages_without_date(self):
        """Test selection skips messages without internalDate."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        mock_gmail = Mock()
        orchestrator.gmail_client = mock_gmail

        message_ids = ["msg_1", "msg_2", "msg_3"]
        mock_gmail.get_message.side_effect = [
            {"id": "msg_1"},  # no internalDate
            {"id": "msg_2", "internalDate": "1625097610000"},  # newest
            {"id": "msg_3", "internalDate": "1625097600000"},
        ]

        selected = orchestrator._select_latest_message(message_ids)
        assert selected == "msg_2"

    def test_error_on_no_valid_messages(self):
        """Test error when no message has valid internalDate."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        mock_gmail = Mock()
        orchestrator.gmail_client = mock_gmail

        message_ids = ["msg_1", "msg_2"]
        mock_gmail.get_message.side_effect = [
            {"id": "msg_1"},  # no internalDate
            {"id": "msg_2"},  # no internalDate
        ]

        with pytest.raises(ValueError, match="No messages with valid internalDate"):
            orchestrator._select_latest_message(message_ids)

    def test_error_on_empty_message_list(self):
        """Test error when message list is empty."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.gmail_client = Mock()

        with pytest.raises(ValueError, match="No messages to select"):
            orchestrator._select_latest_message([])


class TestDeduplicationRegister:
    """Test deduplication registration (see test_fail_safe_integration.py for full tests)."""
    pass


class TestArchiveErrorPropagation:
    """Test that archive errors stop the pipeline."""

    def test_archive_error_propagates(self):
        """Test that _archive_email label resolution error propagates."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.get_or_create_label_id.side_effect = Exception("Label API failed")
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(Exception, match="Label API failed"):
            orchestrator._archive_email("msg_123")

    def test_archive_modify_error_propagates(self):
        """Test that modify error propagates."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.get_or_create_label_id.return_value = "label_id_123"
        mock_service = Mock()
        mock_service.users().messages().modify().execute.side_effect = Exception("Modify API failed")
        mock_gmail.service = mock_service
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(Exception, match="Modify API failed"):
            orchestrator._archive_email("msg_123")


class TestIntegratedPipelineScenarios:
    """Test complete pipeline scenarios (see test_fail_safe_integration.py for full tests)."""
    pass
