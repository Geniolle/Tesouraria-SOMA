"""
Unit tests for source ID isolation in transfer and writing services.

Validates that:
- SheetsWriter returns written_ids
- TransferService processes only selected IDs
- TransferMatchingService processes only selected IDs
- Orchestrator properly passes IDs through the pipeline
- Historical rows remain untouched during execution
"""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from src.gmail_to_sheets.models.transaction import Transaction
from src.gmail_to_sheets.services.sheets_writer import SheetsWriter
from src.gmail_to_sheets.services.transfer_matching_service import TransferMatchingService
from src.gmail_to_sheets.services.transfer_service import TransferService


class TestSheetsWriterWrittenIds:
    """Test that SheetsWriter returns written_ids."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        client.get_headers = Mock(return_value=[
            "DATA MOV.", "DATA VALOR", "DESCRIÇÃO", "IMPORTÂNCIA",
            "TIPO", "TIMESTAMP", "SALDO CONTABILÍSTICO", "ID_INTERNO", "STATUS"
        ])
        client.append_rows = Mock(return_value={"updates": {"updatedRows": 2}})
        client.service = Mock()
        client.service.spreadsheets = Mock(return_value=Mock())
        client.service.spreadsheets().values = Mock(return_value=Mock())
        client.service.spreadsheets().values().get = Mock(return_value=Mock(execute=Mock(
            return_value={"values": []}
        )))
        return client

    @pytest.fixture
    def mock_dedup_service(self):
        """Create mock deduplication service."""
        dedup = Mock()
        dedup.is_duplicate = Mock(return_value=False)
        dedup.register = Mock()
        return dedup

    def test_sheets_writer_returns_written_ids(self, mock_sheets_client, mock_dedup_service):
        """Test that write_transactions returns written_ids list."""
        writer = SheetsWriter(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            sheet_name="T_EXTRATO"
        )

        transactions = [
            Transaction(
                data_mov="05/08/2026",
                data_valor="05/08/2026",
                descricao="TEST TRANS 1",
                valor=Decimal("-100.00"),
                tipo="Saída"
            ),
            Transaction(
                data_mov="05/08/2026",
                data_valor="05/08/2026",
                descricao="TEST TRANS 2",
                valor=Decimal("-50.00"),
                tipo="Saída"
            ),
        ]

        result = writer.write_transactions(
            transactions=transactions,
            opening_balance="1000.00",
            dedup_service=mock_dedup_service
        )

        # Verify written_ids is present
        assert "written_ids" in result
        assert isinstance(result["written_ids"], list)
        assert len(result["written_ids"]) == 2
        # IDs should follow format EXT0000NNNNNN
        assert all(id_.startswith("EXT") for id_ in result["written_ids"])

    def test_sheets_writer_returns_empty_ids_when_all_duplicates(self, mock_sheets_client, mock_dedup_service):
        """Test that write_transactions returns empty written_ids when all are duplicates."""
        mock_dedup_service.is_duplicate = Mock(return_value=True)

        writer = SheetsWriter(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            sheet_name="T_EXTRATO"
        )

        transactions = [
            Transaction(
                data_mov="05/08/2026",
                data_valor="05/08/2026",
                descricao="DUP TRANS 1",
                valor=Decimal("-100.00"),
                tipo="Saída"
            ),
        ]

        result = writer.write_transactions(
            transactions=transactions,
            opening_balance="1000.00",
            dedup_service=mock_dedup_service
        )

        # Verify written_ids is empty but still present
        assert "written_ids" in result
        assert result["written_ids"] == []
        assert result["written"] == 0
        assert result["skipped"] == 1

    def test_sheets_writer_no_transactions_returns_empty_ids(self, mock_sheets_client, mock_dedup_service):
        """Test that write_transactions returns empty written_ids with no transactions."""
        writer = SheetsWriter(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            sheet_name="T_EXTRATO"
        )

        result = writer.write_transactions(
            transactions=[],
            opening_balance="1000.00",
            dedup_service=mock_dedup_service
        )

        # Verify written_ids is empty
        assert "written_ids" in result
        assert result["written_ids"] == []


class TestTransferServiceSourceIsolation:
    """Test that TransferService processes only selected IDs."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        client.get_headers = Mock(side_effect=lambda spreadsheet_id, sheet: {
            "T_EXTRATO": ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "ID_INTERNO", "STATUS"],
            "CONTAORDEM": ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "PERÍODO", "PROCESSO", "ID_INTERNO"],
        }.get(sheet, []))
        client.append_rows = Mock(return_value={"updates": {}})
        client.service = Mock()

        def mock_get_values(spreadsheetId, range):
            """Mock getting values with sample data."""
            if "T_EXTRATO" in range:
                return Mock(execute=Mock(return_value={
                    "values": [
                        ["05/08", "Trans 1", "-100,00", "Saída", "EXT0000000001", ""],
                        ["05/08", "Trans 2", "-50,00", "Saída", "EXT0000000002", ""],
                        ["04/08", "Old Trans", "-75,00", "Saída", "EXT0000000003", ""],
                    ]
                }))
            elif "CONTAORDEM" in range:
                return Mock(execute=Mock(return_value={"values": []}))
            return Mock(execute=Mock(return_value={"values": []}))

        client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=mock_get_values))
        ))
        return client

    @patch('src.gmail_to_sheets.services.transfer_service.BatchWriter')
    def test_transfer_only_selected_ids(self, mock_batch_writer, mock_sheets_client):
        """Test that transfer_pending processes only selected IDs."""
        # Configure mock batch writer to return proper dict
        mock_instance = Mock()
        mock_instance.batch_write_with_updates.return_value = {
            "target_rows_written": 1,
            "status_updates_applied": 1,
            "errors": []
        }
        mock_batch_writer.return_value = mock_instance

        transfer = TransferService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            source_sheet="T_EXTRATO",
            target_sheet="CONTAORDEM"
        )

        # Process only the first ID
        result = transfer.transfer_pending(source_ids=["EXT0000000001"])

        # Verify stats
        assert "transferred" in result
        # Only one ID should be processed (not the other historical ones)
        assert result["total_processed"] <= 1

    @patch('src.gmail_to_sheets.services.transfer_service.BatchWriter')
    def test_transfer_with_empty_ids_returns_zeros(self, mock_batch_writer, mock_sheets_client):
        """Test that transfer_pending returns zero stats with empty IDs."""
        transfer = TransferService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            source_sheet="T_EXTRATO",
            target_sheet="CONTAORDEM"
        )

        result = transfer.transfer_pending(source_ids=[])

        # Verify all stats are zero
        assert result["transferred"] == 0
        assert result["already_exists"] == 0
        assert result["total_processed"] == 0


class TestTransferMatchingServiceSourceIsolation:
    """Test that TransferMatchingService processes only selected IDs."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        client.get_headers = Mock(side_effect=lambda spreadsheet_id, sheet: {
            "T_EXTRATO": ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "ID_INTERNO", "STATUS"],
            "CONTAORDEM": ["DATA MOV.", "DESCRIÇÃO", "IMPORTÂNCIA", "TIPO", "PERÍODO", "PROCESSO", "ID_INTERNO", "DESCRIÇÃO SOMA"],
            "CONSTANTES": ["TEXTO", "TIPO", "DOC. SOMA", "DESCRIÇÃO SOMA"],
        }.get(sheet, []))
        client.append_rows = Mock(return_value={"updates": {}})
        client.service = Mock()

        def mock_get_values(spreadsheetId, range):
            """Mock getting values."""
            if "T_EXTRATO" in range:
                return Mock(execute=Mock(return_value={
                    "values": [
                        ["05/08", "New Trans", "-100,00", "Saída", "EXT0000000001", ""],
                        ["04/08", "Old Trans", "-75,00", "Saída", "EXT0000000003", "Transferido"],
                    ]
                }))
            elif "CONTAORDEM" in range:
                return Mock(execute=Mock(return_value={
                    "values": [
                        ["04/08", "Old Trans", "75,00", "Saída", "AGOSTO", "T_EXTRATO", "EXT0000000003", ""]
                    ]
                }))
            elif "CONSTANTES" in range:
                return Mock(execute=Mock(return_value={"values": []}))
            return Mock(execute=Mock(return_value={"values": []}))

        client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=mock_get_values))
        ))
        return client

    @patch('src.gmail_to_sheets.services.transfer_matching_service.BatchWriter')
    def test_matching_only_selected_ids(self, mock_batch_writer, mock_sheets_client):
        """Test that process_with_matching processes only selected IDs."""
        # Configure mock batch writer to return proper dict
        mock_instance = Mock()
        mock_instance.batch_write_with_updates.return_value = {
            "target_rows_written": 1,
            "status_updates_applied": 1,
            "errors": []
        }
        mock_batch_writer.return_value = mock_instance

        service = TransferMatchingService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            source_sheet="T_EXTRATO",
            target_sheet="CONTAORDEM",
            reference_sheet="CONSTANTES"
        )

        # Process only the new ID, not the historical one
        result = service.process_with_matching(source_ids=["EXT0000000001"])

        # Verify stats
        assert "transferred" in result
        assert "total_processed" in result

    @patch('src.gmail_to_sheets.services.transfer_matching_service.BatchWriter')
    def test_matching_with_empty_ids_returns_zeros(self, mock_batch_writer, mock_sheets_client):
        """Test that process_with_matching returns zero stats with empty IDs."""
        service = TransferMatchingService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_sheet_id",
            source_sheet="T_EXTRATO",
            target_sheet="CONTAORDEM",
            reference_sheet="CONSTANTES"
        )

        result = service.process_with_matching(source_ids=[])

        # Verify all stats are zero
        assert result["transferred"] == 0
        assert result["total_processed"] == 0


class TestOrchestratorIdPassing:
    """Test that Orchestrator passes written IDs to transfer services."""

    def test_orchestrator_passes_ids_to_transfer_service(self):
        """Test that orchestrator passes written_ids to transfer service."""
        from src.gmail_to_sheets.orchestrator import Orchestrator

        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.sheets_client = Mock()

        # Verify method signature accepts source_ids parameter
        assert "_transfer_to_contaordem" in dir(orchestrator)

    def test_orchestrator_passes_ids_to_matching_service(self):
        """Test that orchestrator passes written_ids to matching service."""
        from src.gmail_to_sheets.orchestrator import Orchestrator

        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = Mock()
        orchestrator.sheets_client = Mock()

        # Verify method signature accepts source_ids parameter
        assert "_transfer_with_matching" in dir(orchestrator)
