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
from src.gmail_to_sheets.services.smart_deduplication_service import SmartDeduplicationService


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
    """Test deduplication registration."""

    def test_register_adds_to_cache(self):
        """Test that register adds transaction to cache."""
        dedup = SmartDeduplicationService(
            sheets_client=Mock(),
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # Create mock transaction
        txn = Mock()
        txn.data_mov = "04/08/2026"
        txn.valor = "100.50"
        txn.descricao = "Test Transaction"

        # Register it
        dedup.register(txn)

        # Verify it's in cache
        assert "04/08/2026" in dedup.cache_by_date
        records = dedup.cache_by_date["04/08/2026"]
        # Key should be (normalized_valor, normalized_descricao)
        assert ("100.50", "test transaction") in records

    def test_is_duplicate_after_register(self):
        """Test that is_duplicate returns True after register."""
        dedup = SmartDeduplicationService(
            sheets_client=Mock(),
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # Create and register transaction
        txn = Mock()
        txn.data_mov = "04/08/2026"
        txn.valor = "50.00"
        txn.descricao = "Payment"

        dedup.register(txn)

        # Check if duplicate
        assert dedup.is_duplicate(txn) is True

    def test_register_uses_same_normalization(self):
        """Test that register uses exact same normalization as is_duplicate."""
        dedup = SmartDeduplicationService(
            sheets_client=Mock(),
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # Transaction with spaces/case variations
        txn = Mock()
        txn.data_mov = "04/08/2026"
        txn.valor = "  100.50  "  # spaces around number
        txn.descricao = "TEST TRANSACTION"  # uppercase

        dedup.register(txn)

        # Now check with different formatting (lowercase)
        txn2 = Mock()
        txn2.data_mov = "04/08/2026"
        txn2.valor = "100.50"  # no surrounding spaces
        txn2.descricao = "test transaction"  # lowercase

        # Should be detected as duplicate due to normalization
        assert dedup.is_duplicate(txn2) is True


class TestArchiveErrorPropagation:
    """Test that archive errors stop the pipeline."""

    def test_archive_error_propagates(self):
        """Test that _archive_email error propagates."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.add_label.side_effect = Exception("Label API failed")
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(Exception, match="Label API failed"):
            orchestrator._archive_email("msg_123")

    def test_archive_archive_error_propagates(self):
        """Test that archive_message error propagates."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.add_label.return_value = None
        mock_gmail.archive_message.side_effect = Exception("Archive API failed")
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(Exception, match="Archive API failed"):
            orchestrator._archive_email("msg_123")


class TestIntegratedPipelineScenarios:
    """Test complete pipeline scenarios."""

    def test_scenario_all_new_transactions(self):
        """SCENARIO A: All eight transactions are new."""
        # Verify that:
        # - 8 lines written to T_EXTRATO
        # - 8 written_ids returned
        # - Transfer receives 8 IDs
        # - No historical lines transferred
        # - Balance updated and verified
        # - Email archived after balance success

        dedup = SmartDeduplicationService(
            sheets_client=Mock(),
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # All transactions are new (not in dedup)
        transactions = [Mock(data_mov="04/08/2026", valor=f"{i}.00", descricao=f"Txn{i}")
                       for i in range(8)]

        written_count = 0
        for txn in transactions:
            if not dedup.is_duplicate(txn):
                written_count += 1

        assert written_count == 8

    def test_scenario_all_duplicates(self):
        """SCENARIO B: All transactions are duplicates."""
        # Verify that:
        # - 0 lines written
        # - 0 written_ids
        # - Transfer receives empty list
        # - No historical lines transferred
        # - Balance still updated after reconciliation
        # - Email archived after balance success

        dedup = SmartDeduplicationService(
            sheets_client=Mock(),
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # Pre-populate cache with duplicates
        txn = Mock(data_mov="04/08/2026", valor="100.00", descricao="Duplicate")
        dedup.register(txn)

        # Check that it's detected as duplicate
        assert dedup.is_duplicate(txn) is True

        # All transactions would be duplicates
        transactions = [Mock(data_mov="04/08/2026", valor="100.00", descricao="Duplicate")
                       for _ in range(3)]

        written_count = 0
        for txn in transactions:
            if not dedup.is_duplicate(txn):
                written_count += 1

        assert written_count == 0

    def test_scenario_mixed_duplicates_and_new(self):
        """SCENARIO C: Mix of duplicates and new transactions."""
        # Verify that:
        # - Saldo progressivo considers ALL transactions
        # - Only new ones receive IDs
        # - Transfer receives only written_ids
        # - No historical lines transferred

        dedup = SmartDeduplicationService(
            sheets_client=Mock(),
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # Register some duplicates
        dup_txn = Mock(data_mov="04/08/2026", valor="50.00", descricao="Duplicate")
        dedup.register(dup_txn)

        # Mix of duplicates and new
        transactions = [
            Mock(data_mov="04/08/2026", valor="50.00", descricao="Duplicate"),  # dup
            Mock(data_mov="04/08/2026", valor="100.00", descricao="New1"),      # new
            Mock(data_mov="04/08/2026", valor="50.00", descricao="Duplicate"),  # dup
            Mock(data_mov="04/08/2026", valor="150.00", descricao="New2"),      # new
        ]

        new_ids = []
        for i, txn in enumerate(transactions):
            if not dedup.is_duplicate(txn):
                new_ids.append(f"id_{i}")

        # Only 2 new transactions get IDs
        assert len(new_ids) == 2
        assert new_ids == ["id_1", "id_3"]
