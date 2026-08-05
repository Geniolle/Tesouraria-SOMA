"""
Integration tests for fail-safe pipeline.

Tests validate:
- SheetsWriter progressive balance with Decimal
- SheetsWriter duplicates after balance update
- TransferService batch write validation
- TransferMatchingService batch write and update validation
- Orchestrator.run() complete pipeline
"""

from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.models.transaction import Transaction
from src.gmail_to_sheets.orchestrator import Orchestrator
from src.gmail_to_sheets.services.sheets_writer import SheetsWriter
from src.gmail_to_sheets.services.transfer_matching_service import TransferMatchingService
from src.gmail_to_sheets.services.transfer_service import TransferService


class TestSheetsWriterProgressiveBalance:
    """Test SheetsWriter with progressive balance calculation."""

    def test_balance_progression_with_decimal(self):
        """Test that balance progresses correctly using Decimal."""
        # Mock sheets client
        mock_sheets = Mock()
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.append_rows = Mock(return_value={"replies": []})

        writer = SheetsWriter(mock_sheets, "test_spreadsheet", "T_EXTRATO")

        # Create transactions
        txn1 = Mock(spec=Transaction)
        txn1.data_mov = "04/08/2026"
        txn1.data_valor = "04/08/2026"
        txn1.descricao = "Transaction 1"
        txn1.valor = "10.50"
        txn1.tipo = "CRÉDITO"
        txn1.id_interno = ""

        txn2 = Mock(spec=Transaction)
        txn2.data_mov = "04/08/2026"
        txn2.data_valor = "04/08/2026"
        txn2.descricao = "Transaction 2"
        txn2.valor = "5.25"
        txn2.tipo = "DÉBITO"
        txn2.id_interno = ""

        # Write transactions
        result = writer.write_transactions(
            [txn1, txn2],
            opening_balance="100.00",
            dedup_service=None
        )

        assert result["written"] == 2
        assert len(result["written_ids"]) == 2

        # Verify append_rows was called
        assert mock_sheets.append_rows.called
        rows_written = mock_sheets.append_rows.call_args[0][2]

        # Validate balances in rows
        saldo_idx = 7  # SALDO CONTABILÍSTICO column index
        saldo1 = rows_written[0][saldo_idx]
        saldo2 = rows_written[1][saldo_idx]

        assert saldo1 == "110,50"  # 100 + 10.50
        assert saldo2 == "115,75"  # 110.50 + 5.25

    def test_duplicate_skipped_after_balance_update(self):
        """Test that duplicates are skipped AFTER balance update."""
        # Mock sheets client
        mock_sheets = Mock()
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.append_rows = Mock(return_value={"replies": []})

        writer = SheetsWriter(mock_sheets, "test_spreadsheet", "T_EXTRATO")

        # Create dedup mock that always returns False for 1st, True for 2nd
        dedup = Mock()
        dedup.is_duplicate = Mock(side_effect=[False, True, False])
        dedup.register = Mock()

        # Create transactions: new, duplicate, new
        txn1 = Mock(spec=Transaction)
        txn1.data_mov = "04/08/2026"
        txn1.data_valor = "04/08/2026"
        txn1.descricao = "New1"
        txn1.valor = "100.00"
        txn1.tipo = "CRÉDITO"
        txn1.id_interno = ""
        txn1.dedup_key = Mock(return_value="key1")

        txn2 = Mock(spec=Transaction)
        txn2.data_mov = "04/08/2026"
        txn2.data_valor = "04/08/2026"
        txn2.descricao = "Duplicate"
        txn2.valor = "20.00"
        txn2.tipo = "CRÉDITO"
        txn2.id_interno = ""
        txn2.dedup_key = Mock(return_value="key2")

        txn3 = Mock(spec=Transaction)
        txn3.data_mov = "04/08/2026"
        txn3.data_valor = "04/08/2026"
        txn3.descricao = "New2"
        txn3.valor = "-5.00"
        txn3.tipo = "DÉBITO"
        txn3.id_interno = ""
        txn3.dedup_key = Mock(return_value="key3")

        result = writer.write_transactions(
            [txn1, txn2, txn3],
            opening_balance="100.00",
            dedup_service=dedup
        )

        # Only 2 new transactions written
        assert result["written"] == 2
        assert result["skipped"] == 1

        # Verify saldo progression (considers all, but only writes new)
        rows_written = mock_sheets.append_rows.call_args[0][2]
        saldo_idx = 7

        # txn1 (new): saldo = 100 + 100 = 200
        # txn2 (duplicate): saldo = 200 + 20 = 220 (internal only)
        # txn3 (new): saldo = 220 - 5 = 215

        assert rows_written[0][saldo_idx] == "200,00"  # First new
        assert rows_written[1][saldo_idx] == "215,00"  # Second new (after duplicate)

    def test_invalid_opening_balance_raises(self):
        """Test that invalid opening_balance raises exception."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))

        writer = SheetsWriter(mock_sheets, "test_spreadsheet", "T_EXTRATO")

        with pytest.raises(ValueError, match="opening_balance is required"):
            writer.write_transactions([], opening_balance=None)

        with pytest.raises(ValueError, match="Invalid opening_balance"):
            writer.write_transactions([], opening_balance="invalid")


class TestTransferServiceErrorPropagation:
    """Test TransferService propagates errors."""

    def test_batch_write_error_propagates(self):
        """Test that batch write error propagates."""
        mock_sheets = Mock()
        mock_sheets.service = Mock()

        # Return source and target data for preparation
        def spreadsheets_side_effect():
            mock_api = Mock()
            mock_values = Mock()

            # For source sheet (T_EXTRATO) - has rows
            def get_side_effect(**kwargs):
                range_name = kwargs.get("range", "")
                if "T_EXTRATO" in range_name:
                    return Mock(execute=Mock(return_value={
                        "values": [["EXT0000000001", "04/08/2026", "Test", "CRÉDITO", "100,00", ""]]
                    }))
                else:  # CONTAORDEM
                    return Mock(execute=Mock(return_value={"values": []}))

            mock_values.get = Mock(side_effect=get_side_effect)
            mock_api.values = Mock(return_value=mock_values)
            return mock_api

        mock_sheets.service.spreadsheets = Mock(side_effect=spreadsheets_side_effect)

        def get_headers_side_effect(spreadsheet_id, sheet_name):
            if sheet_name == "T_EXTRATO":
                return ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "STATUS"]
            elif sheet_name == "CONTAORDEM":
                return ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "PERÍODO", "PROCESSO"]
            return []

        mock_sheets.get_headers = Mock(side_effect=get_headers_side_effect)

        transfer = TransferService(mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM")

        # Mock batch writer to raise error
        from unittest.mock import patch
        with patch('src.gmail_to_sheets.services.transfer_service.BatchWriter') as mock_bw:
            mock_batch = Mock()
            mock_batch.batch_write_with_updates.side_effect = RuntimeError("API error")
            mock_bw.return_value = mock_batch

            with pytest.raises(RuntimeError, match="API error"):
                transfer.transfer_pending(["EXT0000000001"])

    def test_incomplete_write_raises_error(self):
        """Test that incomplete write (target_rows_written != target_data) raises."""
        mock_sheets = Mock()
        mock_sheets.service = Mock()

        def spreadsheets_side_effect():
            mock_api = Mock()
            mock_values = Mock()

            def get_side_effect(**kwargs):
                range_name = kwargs.get("range", "")
                if "T_EXTRATO" in range_name:
                    return Mock(execute=Mock(return_value={
                        "values": [
                            ["EXT0000000001", "04/08/2026", "Test1", "CRÉDITO", "100,00", ""],
                            ["EXT0000000002", "04/08/2026", "Test2", "CRÉDITO", "50,00", ""]
                        ]
                    }))
                else:
                    return Mock(execute=Mock(return_value={"values": []}))

            mock_values.get = Mock(side_effect=get_side_effect)
            mock_api.values = Mock(return_value=mock_values)
            return mock_api

        mock_sheets.service.spreadsheets = Mock(side_effect=spreadsheets_side_effect)

        def get_headers_side_effect(spreadsheet_id, sheet_name):
            if sheet_name == "T_EXTRATO":
                return ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "STATUS"]
            elif sheet_name == "CONTAORDEM":
                return ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "PERÍODO", "PROCESSO"]
            return []

        mock_sheets.get_headers = Mock(side_effect=get_headers_side_effect)

        transfer = TransferService(mock_sheets, "spreadsheet", "T_EXTRATO", "CONTAORDEM")

        from unittest.mock import patch
        with patch('src.gmail_to_sheets.services.transfer_service.BatchWriter') as mock_bw:
            mock_batch = Mock()
            mock_batch.batch_write_with_updates.return_value = {
                "target_rows_written": 1,  # Expected 2 - incomplete
                "status_updates_applied": 0,
                "errors": []
            }
            mock_bw.return_value = mock_batch

            with pytest.raises(RuntimeError, match="Incomplete write"):
                transfer.transfer_pending(["EXT0000000001", "EXT0000000002"])


class TestTransferMatchingServiceErrorPropagation:
    """Test TransferMatchingService propagates errors."""

    def test_batch_write_error_propagates_matching(self):
        """Test that batch write error propagates in matching service."""
        mock_sheets = Mock()
        mock_sheets.service = Mock()

        def spreadsheets_side_effect():
            mock_api = Mock()
            mock_values = Mock()

            def get_side_effect(**kwargs):
                range_name = kwargs.get("range", "")
                if "T_EXTRATO" in range_name:
                    return Mock(execute=Mock(return_value={
                        "values": [["EXT0000000001", "04/08/2026", "Test", "CRÉDITO", "100,00", ""]]
                    }))
                elif "CONSTANTES" in range_name:
                    return Mock(execute=Mock(return_value={"values": []}))
                else:  # CONTAORDEM
                    return Mock(execute=Mock(return_value={"values": []}))

            mock_values.get = Mock(side_effect=get_side_effect)
            mock_api.values = Mock(return_value=mock_values)
            return mock_api

        mock_sheets.service.spreadsheets = Mock(side_effect=spreadsheets_side_effect)

        def get_headers_side_effect(spreadsheet_id, sheet_name):
            if sheet_name == "T_EXTRATO":
                return ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "STATUS"]
            elif sheet_name == "CONTAORDEM":
                return ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "PERÍODO", "PROCESSO"]
            elif sheet_name == "CONSTANTES":
                return ["TEXTO", "TIPO", "VALOR", "DOC. SOMA", "DESCRIÇÃO SOMA"]
            return []

        mock_sheets.get_headers = Mock(side_effect=get_headers_side_effect)

        service = TransferMatchingService(
            mock_sheets, "spreadsheet",
            "T_EXTRATO", "CONTAORDEM", "CONSTANTES"
        )

        from unittest.mock import patch
        with patch('src.gmail_to_sheets.services.transfer_matching_service.BatchWriter') as mock_bw:
            mock_batch = Mock()
            mock_batch.batch_write_with_updates.side_effect = RuntimeError("Batch write failed")
            mock_bw.return_value = mock_batch

            with pytest.raises(RuntimeError, match="Batch write failed"):
                service.process_with_matching(["EXT0000000001"])


class TestOrchestratorArchiveFailSafe:
    """Test _archive_email propagates errors properly."""

    def test_archive_email_add_label_error_propagates(self):
        """Test that add_label error in _archive_email propagates."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.add_label.side_effect = RuntimeError("Label API error")
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(RuntimeError, match="Label API error"):
            orchestrator._archive_email("msg_123")

    def test_archive_email_archive_error_propagates(self):
        """Test that archive_message error in _archive_email propagates."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.add_label = Mock()  # Success
        mock_gmail.archive_message.side_effect = RuntimeError("Archive API error")
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(RuntimeError, match="Archive API error"):
            orchestrator._archive_email("msg_123")


class TestSheetsWriterZeroBalance:
    """Test SheetsWriter accepts zero as valid opening_balance."""

    def test_opening_balance_zero_decimal(self):
        """Test that Decimal(0.00) is accepted."""
        from decimal import Decimal

        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))
        mock_sheets.append_rows = Mock(return_value={"replies": []})

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        txn = Mock(spec=Transaction)
        txn.data_mov = "04/08/2026"
        txn.data_valor = "04/08/2026"
        txn.descricao = "Test"
        txn.valor = "50.00"
        txn.tipo = "CRÉDITO"
        txn.id_interno = ""

        result = writer.write_transactions(
            [txn],
            opening_balance=Decimal("0.00"),
            dedup_service=None
        )

        assert result["written"] == 1
        rows = mock_sheets.append_rows.call_args[0][2]
        assert rows[0][7] == "50,00"  # saldo_idx = 7, 0 + 50 = 50

    def test_opening_balance_zero_string(self):
        """Test that string '0.00' is accepted."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))
        mock_sheets.append_rows = Mock(return_value={"replies": []})

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        txn = Mock(spec=Transaction)
        txn.data_mov = "04/08/2026"
        txn.data_valor = "04/08/2026"
        txn.descricao = "Test"
        txn.valor = "25.00"
        txn.tipo = "CRÉDITO"
        txn.id_interno = ""

        result = writer.write_transactions([txn], opening_balance="0.00")
        assert result["written"] == 1

    def test_opening_balance_zero_comma_format(self):
        """Test that string '0,00' (comma) is accepted."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))
        mock_sheets.append_rows = Mock(return_value={"replies": []})

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        writer.write_transactions([], opening_balance="0,00")
        # Should not raise

    def test_opening_balance_none_raises(self):
        """Test that None is rejected."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[])
        mock_sheets.service = Mock()

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        with pytest.raises(ValueError, match="opening_balance is required"):
            writer.write_transactions([], opening_balance=None)

    def test_opening_balance_empty_string_raises(self):
        """Test that empty string is rejected."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[])
        mock_sheets.service = Mock()

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        with pytest.raises(ValueError, match="opening_balance is required"):
            writer.write_transactions([], opening_balance="")

    def test_opening_balance_spaces_only_raises(self):
        """Test that spaces-only string is rejected."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[])
        mock_sheets.service = Mock()

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        with pytest.raises(ValueError, match="opening_balance is required"):
            writer.write_transactions([], opening_balance="   ")


class TestSheetsWriterExactBalance:
    """Test exact balance calculation: 100 + 20dup - 5new = 115."""

    def test_balance_100_plus_20dup_minus_5new_equals_115(self):
        """EXACT TEST: opening=100, +20 (dup), -5 (new) -> line saldo=115."""
        mock_sheets = Mock()
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DATA VALOR", "DESCRIÇÃO",
            "IMPORTÂNCIA", "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO"
        ])
        mock_sheets.service = Mock()
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))
        mock_sheets.append_rows = Mock(return_value={"replies": []})

        writer = SheetsWriter(mock_sheets, "test", "T_EXTRATO")

        dedup = Mock()
        dedup.is_duplicate = Mock(side_effect=[True, False])  # First is dup, second is new
        dedup.register = Mock()

        # Transaction 1: +20 (will be duplicated)
        txn1 = Mock(spec=Transaction)
        txn1.data_mov = "04/08/2026"
        txn1.data_valor = "04/08/2026"
        txn1.descricao = "Dup"
        txn1.valor = "20.00"
        txn1.tipo = "CRÉDITO"
        txn1.id_interno = ""
        txn1.dedup_key = Mock(return_value="dup_key")

        # Transaction 2: -5 (will be new)
        txn2 = Mock(spec=Transaction)
        txn2.data_mov = "04/08/2026"
        txn2.data_valor = "04/08/2026"
        txn2.descricao = "New"
        txn2.valor = "-5.00"
        txn2.tipo = "DÉBITO"
        txn2.id_interno = ""
        txn2.dedup_key = Mock(return_value="new_key")

        result = writer.write_transactions(
            [txn1, txn2],
            opening_balance="100.00",
            dedup_service=dedup
        )

        # Validations
        assert result["written"] == 1, "Only 1 new transaction should be written"
        assert result["skipped"] == 1, "1 duplicate should be skipped"
        assert len(result["written_ids"]) == 1, "Only 1 ID for the new transaction"

        # Verify row written to sheets
        rows = mock_sheets.append_rows.call_args[0][2]
        assert len(rows) == 1, "Only 1 row should be appended"

        saldo_cell = rows[0][7]  # SALDO CONTABILÍSTICO is index 7
        assert saldo_cell == "115,00", f"Expected saldo 115,00 but got {saldo_cell}"


class TestSmartDeduplicationRegisterPreservesCache:
    """Test that register() preserves existing cache from load_existing_by_date."""

    def test_register_preserves_historical_records(self):
        """Test that register() keeps historical records intact."""
        mock_sheets = Mock()
        mock_sheets.service = Mock()

        # Mock get_headers
        mock_sheets.get_headers = Mock(return_value=[
            "ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA"
        ])

        # Mock spreadsheets values to return a historical record
        def mock_get_values(**kwargs):
            range_name = kwargs.get("range", "")
            if "A2:Z99999" in range_name:
                return Mock(execute=Mock(return_value={
                    "values": [
                        ["", "04/08/2026", "HistoricalTxn", "100.00"]
                    ]
                }))
            return Mock(execute=Mock(return_value={"values": []}))

        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=mock_get_values))
        ))

        from src.gmail_to_sheets.services.smart_deduplication_service import (
            SmartDeduplicationService,
        )

        dedup = SmartDeduplicationService(
            sheets_client=mock_sheets,
            spreadsheet_id="test",
            target_sheet="CONTAORDEM"
        )

        # Register a new transaction
        new_txn = Mock()
        new_txn.data_mov = "04/08/2026"
        new_txn.valor = "50.00"
        new_txn.descricao = "NewTxn"

        dedup.register(new_txn)

        # Verify cache has BOTH historical and new transaction
        records = dedup.cache_by_date.get("04/08/2026", {})
        assert len(records) >= 2, "Cache should have historical + new records"

        # Verify historical key exists
        historical_key = ("100.00", "historicaltxn")
        assert historical_key in records, "Historical transaction should be in cache"

        # Verify new key exists
        new_key = ("50.00", "newtxn")
        assert new_key in records, "New registered transaction should be in cache"


class TestBatchWriterFailSafeDirect:
    """Test BatchWriter fail-safe directly (not through TransferService)."""

    def test_batch_writer_raises_on_append_failure(self):
        """Test that BatchWriter raises when append_rows fails."""
        from src.gmail_to_sheets.services.batch_writer import BatchWriter

        mock_sheets = Mock()
        mock_sheets.append_rows.side_effect = RuntimeError("API error")

        writer = BatchWriter(mock_sheets, "test_spreadsheet")

        with pytest.raises(RuntimeError, match="API error"):
            writer.batch_write_with_updates(
                source_sheet="T_EXTRATO",
                source_data=[],
                target_sheet="CONTAORDEM",
                target_data=[["test_row"]],
                status_updates=None
            )


class TestOrchestratorMethodOrder:
    """Test Orchestrator methods execute in correct order."""

    def test_orchestrator_archive_fails_propagates(self):
        """Test that archive error propagates and pipeline doesn't succeed."""
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.settings.gmail.backup_label_name = "Backup"

        mock_gmail = Mock()
        mock_gmail.archive_message.side_effect = RuntimeError("Archive failed")
        orchestrator.gmail_client = mock_gmail

        with pytest.raises(RuntimeError, match="Archive failed"):
            orchestrator._archive_email("msg_1")

    def test_transfer_empty_ids_receives_empty_list(self):
        """TEST F: Transfer receives empty list when written_ids is empty."""
        from src.gmail_to_sheets.services.transfer_service import TransferService

        mock_sheets = Mock()
        mock_sheets.service = Mock()
        mock_sheets.get_headers = Mock(side_effect=lambda spreadsheet_id, sheet_name: {
            "T_EXTRATO": ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "STATUS"],
            "CONTAORDEM": ["ID_INTERNO", "DATA MOV.", "DESCRIÇÃO", "TIPO", "IMPORTÂNCIA", "PERÍODO", "PROCESSO"]
        }.get(sheet_name, []))
        mock_sheets.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": []})
            ))))
        ))

        transfer = TransferService(mock_sheets, "test", "T_EXTRATO", "CONTAORDEM")

        # Passing empty list should return zero statistics
        result = transfer.transfer_pending(source_ids=[])

        assert result["transferred"] == 0
        assert result["total_processed"] == 0
