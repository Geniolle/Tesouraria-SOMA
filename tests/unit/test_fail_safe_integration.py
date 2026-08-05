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
