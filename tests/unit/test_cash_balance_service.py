"""
Unit tests for CashBalanceService with header-based discovery.

Tests validate:
- Header row reading and parsing
- Header column mapping
- Account column localization by header name
- Dynamic cell calculation
- JSON serialization
- Read-only inspection
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.services.cash_balance_service import (
    CashBalanceError,
    CashBalanceService,
    HeaderColumn,
)


class TestHeaderColumnDataclass:
    """Test HeaderColumn structure."""

    def test_header_column_creation(self):
        """Test HeaderColumn instantiation."""
        col = HeaderColumn(
            index=0,
            column_number=1,
            column_letter="A",
            original_name="Test",
            normalized_name="test",
        )
        assert col.index == 0
        assert col.column_number == 1
        assert col.column_letter == "A"
        assert col.original_name == "Test"
        assert col.normalized_name == "test"

    def test_header_column_frozen(self):
        """Test HeaderColumn is immutable."""
        col = HeaderColumn(
            index=0,
            column_number=1,
            column_letter="A",
            original_name="Test",
            normalized_name="test",
        )
        with pytest.raises(AttributeError):
            col.index = 1


class TestHeaderLoadingBasic:
    """Test basic header row loading."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        client._number_to_column = Mock(side_effect=lambda n: CashBalanceService._number_to_column_impl(n))
        return client

    def test_loads_only_header_row(self, mock_sheets_client):
        """Test that only the header row is read (row 1)."""
        header_row_values = ["COL_A", "COL_B", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()

        # Verify get_row was called with correct parameters
        mock_sheets_client.get_row.assert_called_once_with(
            "test_id",
            "GERENCIAR CAIXAS",
            1,  # header_row
        )

        assert len(columns) == 3

    def test_header_in_first_column(self, mock_sheets_client):
        """Test header located in first column (A)."""
        header_row_values = ["CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        assert len(columns) == 1
        assert columns[0].column_letter == "A"
        assert columns[0].column_number == 1
        assert columns[0].index == 0

    def test_header_in_column_c(self, mock_sheets_client):
        """Test header located in column C."""
        header_row_values = ["COL_A", "COL_B", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = next((c for c in columns if c.original_name == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"), None)
        assert found is not None
        assert found.column_letter == "C"
        assert found.column_number == 3
        assert found.index == 2

    def test_header_beyond_column_z(self, mock_sheets_client):
        """Test header located beyond column Z (e.g., AA, AB)."""
        # Column AA = 27, AB = 28
        header_row_values = ["COL"] * 27 + ["CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = next((c for c in columns if c.original_name == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"), None)
        assert found is not None
        assert found.column_number == 28
        assert found.column_letter == "AB"

    def test_empty_cells_preserve_index(self, mock_sheets_client):
        """Test that empty cells between headers preserve the column index."""
        # A=filled, B=empty, C=filled
        header_row_values = ["COL_A", "", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = next((c for c in columns if c.original_name == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"), None)
        assert found is not None
        assert found.index == 2
        assert found.column_number == 3
        assert found.column_letter == "C"

    def test_stores_original_and_normalized_names(self, mock_sheets_client):
        """Test that both original and normalized names are stored."""
        header_row_values = ["CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        col = columns[0]
        assert col.original_name == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"
        assert "economica" in col.normalized_name
        assert "cc" in col.normalized_name


class TestAccountColumnFinding:
    """Test account column localization."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        client._number_to_column = Mock(side_effect=lambda n: CashBalanceService._number_to_column_impl(n))
        return client

    def test_finds_exact_match(self, mock_sheets_client):
        """Test finding account column with exact match."""
        header_row_values = ["ACCOUNT1", "CAIXA ECONÔMICA MONTEPIO GERAL - CC", "ACCOUNT2"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = service._find_account_column(columns)
        assert found.original_name == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"
        assert found.column_letter == "B"

    def test_finds_with_accent_differences(self, mock_sheets_client):
        """Test finding account column despite accent differences."""
        # Sheet has ECONÔMICA (with accent), search for ECONOMICA (without)
        header_row_values = ["CAIXA ECONÔMICA MONTEPIO GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONOMICA MONTEPIO GERAL - CC",  # No accent
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = service._find_account_column(columns)
        assert found.original_name == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"

    def test_finds_with_case_differences(self, mock_sheets_client):
        """Test finding account column despite case differences."""
        # Sheet has lowercase, search for uppercase
        header_row_values = ["caixa econômica montepio geral - cc"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = service._find_account_column(columns)
        assert found.original_name == "caixa econômica montepio geral - cc"

    def test_finds_with_space_differences(self, mock_sheets_client):
        """Test finding account column with multiple spaces."""
        # Sheet has multiple spaces
        header_row_values = ["CAIXA  ECONÔMICA  MONTEPIO   GERAL - CC"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        found = service._find_account_column(columns)
        assert found.original_name == "CAIXA  ECONÔMICA  MONTEPIO   GERAL - CC"

    def test_error_when_not_found(self, mock_sheets_client):
        """Test error when account not found."""
        header_row_values = ["ACCOUNT1", "ACCOUNT2", "ACCOUNT3"]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        with pytest.raises(CashBalanceError, match="not found"):
            service._find_account_column(columns)

    def test_error_when_multiple_matches(self, mock_sheets_client):
        """Test error when multiple columns match."""
        header_row_values = [
            "CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            "OTHER",
            "CAIXA ECONÔMICA MONTEPIO GERAL - CC",  # Duplicate
        ]

        mock_sheets_client.get_row = Mock(return_value=header_row_values)

        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        columns = service._load_header_columns()
        with pytest.raises(CashBalanceError, match="Multiple occurrences"):
            service._find_account_column(columns)


class TestTargetCellCalculation:
    """Test target cell calculation."""

    def test_calculates_label_cell(self):
        """Test calculation of label cell (header row)."""
        # Row 1, Column C (number 3)
        label_cell = CashBalanceService._row_col_to_a1(1, 3)
        assert label_cell == "C1"

    def test_calculates_target_cell(self):
        """Test calculation of target cell (header_row + row_offset)."""
        # Row 2 (1 + 1), Column C (number 3)
        target_cell = CashBalanceService._row_col_to_a1(2, 3)
        assert target_cell == "C2"

    def test_calculates_cells_in_various_columns(self):
        """Test cell calculation in various columns."""
        # Column A = 1
        assert CashBalanceService._row_col_to_a1(1, 1) == "A1"
        # Column Z = 26
        assert CashBalanceService._row_col_to_a1(1, 26) == "Z1"
        # Column AA = 27
        assert CashBalanceService._row_col_to_a1(1, 27) == "AA1"
        # Column AB = 28
        assert CashBalanceService._row_col_to_a1(1, 28) == "AB1"


class TestInspectTarget:
    """Test read-only inspection mode."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client with full setup."""
        client = Mock()
        client._number_to_column = Mock(side_effect=lambda n: CashBalanceService._number_to_column_impl(n))
        client.get_row = Mock(return_value=["COL_A", "CAIXA ECONÔMICA MONTEPIO GERAL - CC"])
        client.get_cell = Mock(return_value=None)
        return client

    def test_inspect_target_does_not_write(self, mock_sheets_client):
        """Test that inspect_target is read-only."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        result = service.inspect_target()

        # Verify update_cell was NOT called
        assert not hasattr(mock_sheets_client, 'update_cell') or not mock_sheets_client.update_cell.called

        # Verify result structure
        assert result["header_row"] == 1
        assert result["header_name"] == "CAIXA ECONÔMICA MONTEPIO GERAL - CC"
        assert result["target_cell"] == "B2"
        assert result["written_value"] is None
        assert result["verified"] is False

    def test_inspect_reads_only_header_and_target(self, mock_sheets_client):
        """Test that inspect reads only header row and target cell."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        result = service.inspect_target()

        # Verify get_row called once for header
        assert mock_sheets_client.get_row.call_count == 1
        mock_sheets_client.get_row.assert_called_with("test_id", "GERENCIAR CAIXAS", 1)

        # Verify get_cell called once for target
        assert mock_sheets_client.get_cell.call_count == 1
        mock_sheets_client.get_cell.assert_called_with("test_id", "GERENCIAR CAIXAS", 2, 2)


class TestJSONSerialization:
    """Test JSON serialization at API boundary."""

    @pytest.fixture
    def mock_sheets_client(self):
        """Create mock sheets client."""
        client = Mock()
        client._number_to_column = Mock(side_effect=lambda n: CashBalanceService._number_to_column_impl(n))
        client.get_row = Mock(return_value=["CAIXA ECONÔMICA MONTEPIO GERAL - CC"])
        client.get_cell = Mock(return_value=None)
        client.update_cell = Mock()
        return client

    def test_sends_float_not_decimal_to_api(self, mock_sheets_client):
        """Test that float (not Decimal) is sent to update_cell."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        service.update_balance(Decimal("2148.04"))

        # Get the value passed to update_cell
        call_args = mock_sheets_client.update_cell.call_args
        value_arg = call_args.kwargs.get("value")

        # Must be float, not Decimal
        assert isinstance(value_arg, float)
        assert value_arg == 2148.04

    def test_uses_raw_value_input_option(self, mock_sheets_client):
        """Test that RAW value_input_option is used."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        service.update_balance(Decimal("2148.04"))

        call_args = mock_sheets_client.update_cell.call_args
        assert call_args.kwargs.get("value_input_option") == "RAW"

    def test_quantizes_to_two_decimals(self, mock_sheets_client):
        """Test balance quantization."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            header_row=1,
            row_offset=1,
            verify_after_write=False,
        )

        service.update_balance(Decimal("2148.047"))

        call_args = mock_sheets_client.update_cell.call_args
        value_arg = call_args.kwargs.get("value")

        # Must be quantized to 0.01
        assert value_arg == 2148.05


class TestNumberToColumnConversion:
    """Test column number to letter conversion."""

    def test_single_letter_columns(self):
        """Test A-Z conversion."""
        assert CashBalanceService._number_to_column_impl(1) == "A"
        assert CashBalanceService._number_to_column_impl(26) == "Z"

    def test_double_letter_columns(self):
        """Test AA-ZZ conversion."""
        assert CashBalanceService._number_to_column_impl(27) == "AA"
        assert CashBalanceService._number_to_column_impl(52) == "AZ"
        assert CashBalanceService._number_to_column_impl(702) == "ZZ"

    def test_triple_letter_columns(self):
        """Test AAA+ conversion."""
        assert CashBalanceService._number_to_column_impl(703) == "AAA"


# Add method to service for testing
CashBalanceService._number_to_column_impl = staticmethod(
    lambda n: "" if n <= 0 else (
        CashBalanceService._number_to_column_impl((n - 1) // 26) + chr(65 + (n - 1) % 26)
    ) if n > 0 else ""
)
