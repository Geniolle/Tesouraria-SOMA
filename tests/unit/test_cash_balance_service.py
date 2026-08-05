"""
Unit tests for CashBalanceService.

Tests validate:
- Finding the account label dynamically
- Writing balance to the cell below
- Verifying written values
- Error handling for missing/duplicate labels
- Text normalization
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal

from src.gmail_to_sheets.services.cash_balance_service import (
    CashBalanceService,
    CashBalanceError,
)


class TestCashBalanceServiceLabelFinding:
    """Test label finding functionality."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        return client

    def test_finds_label_and_writes_below(self, mock_sheets_client):
        """Test finding label and writing to cell below."""
        # Mock sheet data with label in D5
        sheet_data = [
            ["", "", "", ""],  # Row 0
            ["", "", "", ""],  # Row 1
            ["", "", "", ""],  # Row 2
            ["", "", "", ""],  # Row 3
            ["", "", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"],  # Row 4 (D5)
            ["", "", "", "1000.00"],  # Row 5 (D6) - target
        ]

        mock_sheets_client.service = Mock()
        mock_sheets_client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))
        mock_sheets_client.update_cell = Mock()

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # Verify update_cell was called with correct row/col
        assert mock_sheets_client.update_cell.called
        # Row 5 (0-indexed), Col 3 (0-indexed) = row 6, col 4 (1-indexed for API)
        assert result["label_cell"] == "D5"
        assert result["target_cell"] == "D6"
        assert result["written_value"] == "2148,04"

    def test_normalizes_text_with_accents(self, mock_sheets_client):
        """Test that text normalization handles accents."""
        # Label with different spacing and case
        sheet_data = [
            ["", "", "", "CAIXA ECONOMICA MONTEPIO  GERAL  -  CC"],  # Spaces, no accents
        ]

        mock_sheets_client.service = Mock()
        mock_sheets_client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))
        mock_sheets_client.update_cell = Mock()

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        # Should find despite different case and spacing
        result = service.update_balance(Decimal("2148.04"))
        assert result["label_cell"] == "D1"

    def test_error_when_label_not_found(self, mock_sheets_client):
        """Test error when label not found."""
        sheet_data = [
            ["Data", "Description", "Amount", "Status"],
        ]

        mock_sheets_client.service = Mock()
        mock_sheets_client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        with pytest.raises(CashBalanceError, match="not found"):
            service.update_balance(Decimal("2148.04"))

    def test_error_when_multiple_labels(self, mock_sheets_client):
        """Test error when multiple labels found."""
        sheet_data = [
            ["", "", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"],
            ["", "", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"],  # Duplicate
        ]

        mock_sheets_client.service = Mock()
        mock_sheets_client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        with pytest.raises(CashBalanceError, match="Multiple occurrences"):
            service.update_balance(Decimal("2148.04"))


class TestCashBalanceServiceFormatting:
    """Test balance formatting."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        sheet_data = [
            ["", "", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"],
            ["", "", "", ""],  # Target cell
        ]
        client.service = Mock()
        client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))
        client.update_cell = Mock()
        return client

    def test_formats_balance_with_two_decimals(self, mock_sheets_client):
        """Test balance formatting."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # Format should use comma as decimal separator
        assert result["written_value"] == "2148,04"

    def test_formats_whole_numbers(self, mock_sheets_client):
        """Test formatting of whole numbers."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2000"))

        # Should include .00
        assert result["written_value"] == "2000,00"


class TestCashBalanceServiceVerification:
    """Test verification of written values."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        return client

    def test_verifies_written_value(self, mock_sheets_client):
        """Test verification of value written."""
        # Initial data with empty target cell
        initial_data = [
            ["", "", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"],
            ["", "", "", ""],  # Empty target
        ]

        # After write, cell has the value
        verified_data = [
            ["", "", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"],
            ["", "", "", "2148,04"],  # Value written
        ]

        call_count = [0]

        def mock_get_execute(**kwargs):
            call_count[0] += 1
            # First call returns initial data, second call returns verified data
            if call_count[0] == 1:
                return Mock(execute=Mock(return_value={"values": initial_data}))
            else:
                return Mock(execute=Mock(return_value={"values": verified_data}))

        mock_sheets_client.service = Mock()
        mock_sheets_client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=mock_get_execute))
        ))
        mock_sheets_client.update_cell = Mock()

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=True,
        )

        result = service.update_balance(Decimal("2148.04"))

        assert result["verified"] is True
        assert result["verified_value"] is not None


class TestCashBalanceServiceA1Notation:
    """Test A1 notation conversion."""

    def test_row_col_to_a1(self):
        """Test row/col to A1 conversion."""
        service = CashBalanceService.__new__(CashBalanceService)

        # Test various conversions
        assert service._row_col_to_a1(0, 0) == "A1"  # First cell
        assert service._row_col_to_a1(4, 3) == "D5"  # Row 5, Col D
        assert service._row_col_to_a1(25, 0) == "A26"  # Row 26
        assert service._row_col_to_a1(0, 25) == "Z1"  # Column Z


class TestCashBalanceServiceNormalization:
    """Test text normalization."""

    def test_normalize_text_case(self):
        """Test case folding."""
        service = CashBalanceService.__new__(CashBalanceService)

        normalized = service._normalize_text("CAIXA ECONÔMICA")
        assert normalized == normalized.casefold()

    def test_normalize_text_accents(self):
        """Test accent removal."""
        service = CashBalanceService.__new__(CashBalanceService)

        # Should normalize é to e
        text_with_accents = "ECONÔMICA"
        normalized = service._normalize_text(text_with_accents)
        # After normalization, should not have accents
        assert "ô" not in normalized

    def test_normalize_text_spaces(self):
        """Test space normalization."""
        service = CashBalanceService.__new__(CashBalanceService)

        text_with_spaces = "CAIXA  ECONÔMICA   MONTEPIO"
        normalized = service._normalize_text(text_with_spaces)
        # Should normalize multiple spaces to single
        assert "  " not in normalized
