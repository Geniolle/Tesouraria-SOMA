"""
Test JSON serialization of cash balance updates.

Validates that:
- Body sent to Google API is JSON-serializable
- Values are float (not Decimal or string)
- value_input_option is RAW
"""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.gmail_to_sheets.services.cash_balance_service import CashBalanceService


class TestCashBalanceJSONSerialization:
    """Test JSON serialization of balance updates."""

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
            get=Mock(return_value=Mock(execute=Mock(return_value={
                "sheets": [{
                    "properties": {
                        "title": "GERENCIAR CAIXAS",
                        "gridProperties": {
                            "rowCount": 1000,
                            "columnCount": 10
                        }
                    }
                }]
            }))),
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))
        client.update_cell = Mock()
        return client

    def test_body_is_json_serializable(self, mock_sheets_client):
        """Test that the body sent to Google API is JSON-serializable."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # Get the value passed to update_cell
        call_args = mock_sheets_client.update_cell.call_args
        value_arg = call_args.kwargs.get("value")

        # Simulate the body that would be sent to Google API
        body = {"values": [[value_arg]]}

        # This should not raise
        json_str = json.dumps(body)

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["values"][0][0] == 2148.04

    def test_value_is_float_not_decimal(self, mock_sheets_client):
        """Test that value sent to API is float, not Decimal."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # Get the value passed to update_cell
        call_args = mock_sheets_client.update_cell.call_args
        value_arg = call_args.kwargs.get("value")

        # Verify type
        assert isinstance(value_arg, float)
        assert not isinstance(value_arg, Decimal)
        assert value_arg == 2148.04

    def test_value_is_not_string(self, mock_sheets_client):
        """Test that value is not string."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # Get the value passed to update_cell
        call_args = mock_sheets_client.update_cell.call_args
        value_arg = call_args.kwargs.get("value")

        # Verify it's not a string
        assert not isinstance(value_arg, str)
        assert not isinstance(value_arg, bytes)

    def test_value_input_option_is_raw(self, mock_sheets_client):
        """Test that value_input_option is explicitly RAW."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # Get the arguments
        call_args = mock_sheets_client.update_cell.call_args

        # Verify value_input_option is RAW
        assert call_args.kwargs.get("value_input_option") == "RAW"

    def test_written_value_is_string_for_display(self, mock_sheets_client):
        """Test that written_value in result is string (for display)."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        result = service.update_balance(Decimal("2148.04"))

        # written_value should be string for display
        assert isinstance(result["written_value"], str)
        # Format: decimal point converted to comma for display
        assert result["written_value"] == "2148,04"
        assert "." not in result["written_value"]


class TestCashBalanceDynamicRange:
    """Test dynamic range calculation."""

    @pytest.fixture
    def mock_sheets_client_with_metadata(self):
        """Create mock sheets client with metadata."""
        client = Mock()
        sheet_data = [
            [""] * 50,  # Wide sheet
        ]
        for i in range(2000):
            sheet_data.append([""] * 50)

        client.service = Mock()
        client.service.spreadsheets = Mock(return_value=Mock(
            get=Mock(return_value=Mock(execute=Mock(return_value={
                "sheets": [{
                    "properties": {
                        "title": "GERENCIAR CAIXAS",
                        "gridProperties": {
                            "rowCount": 2000,
                            "columnCount": 50
                        }
                    }
                }]
            }))),
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": sheet_data})
            ))))
        ))
        client.update_cell = Mock()
        return client

    def test_dynamic_range_includes_actual_dimensions(self, mock_sheets_client_with_metadata):
        """Test that dynamic range is calculated from actual sheet dimensions."""
        service = CashBalanceService(
            sheets_client=mock_sheets_client_with_metadata,
            spreadsheet_id="test_id",
            sheet_name="GERENCIAR CAIXAS",
            account_label="CAIXA ECONÔMICA MONTEPIO GERAL - CC",
            row_offset=1,
            verify_after_write=False,
        )

        # Get dynamic range
        range_name = service._get_dynamic_range()

        # Should include actual dimensions (2000 rows, 50 cols = column AX)
        assert "2000" in range_name
        # Column 50 = AX
        assert "AX" in range_name
        assert range_name.startswith("'GERENCIAR CAIXAS'")

    def test_number_to_column_conversion(self):
        """Test column number to letter conversion."""
        service = CashBalanceService.__new__(CashBalanceService)

        # Test various conversions
        assert service._number_to_column(1) == "A"
        assert service._number_to_column(26) == "Z"
        assert service._number_to_column(27) == "AA"
        assert service._number_to_column(52) == "AZ"
        assert service._number_to_column(53) == "BA"
        assert service._number_to_column(702) == "ZZ"
        assert service._number_to_column(703) == "AAA"
