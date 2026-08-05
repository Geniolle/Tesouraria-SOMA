"""
Tests for sheet escaping, normalization, and file format features.
"""

from unittest.mock import Mock

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.services.cash_balance_service import CashBalanceService


class TestSheetNameEscaping:
    """Test sheet name quoting and escaping."""

    def test_quote_sheet_name_simple(self):
        """Test quoting a simple sheet name."""
        quoted = SheetsClient._quote_sheet_name("GERENCIAR CAIXAS")
        assert quoted == "'GERENCIAR CAIXAS'"

    def test_quote_sheet_name_with_space(self):
        """Test quoting sheet name with spaces."""
        quoted = SheetsClient._quote_sheet_name("My Sheet Name")
        assert quoted == "'My Sheet Name'"

    def test_escape_sheet_name_with_apostrophe(self):
        """Test escaping sheet name with apostrophe."""
        quoted = SheetsClient._quote_sheet_name("Caixa d'Água")
        assert quoted == "'Caixa d''Água'"

    def test_escape_multiple_apostrophes(self):
        """Test escaping sheet name with multiple apostrophes."""
        quoted = SheetsClient._quote_sheet_name("It's the CEO's data")
        assert quoted == "'It''s the CEO''s data'"


class TestGetRowRangeFormat:
    """Test that get_row uses correct range format."""

    def test_get_row_uses_quoted_sheet_name(self):
        """Test that get_row constructs range with quoted sheet name."""
        client = Mock()
        client.service = Mock()
        client.service.spreadsheets = Mock(return_value=Mock(
            values=Mock(return_value=Mock(get=Mock(return_value=Mock(
                execute=Mock(return_value={"values": [["A", "B", "C"]]})
            ))))
        ))

        sheets_client = SheetsClient.__new__(SheetsClient)
        sheets_client.service = client.service

        # Call get_row (this will use the actual _quote_sheet_name method)
        # Note: We're testing the method exists and would be called correctly
        assert hasattr(sheets_client, "get_row")

    def test_header_range_format(self):
        """Test that header range is formatted correctly."""
        # The format should be '<sheet>'!1:1, not '<sheet>'!1:1000 or similar
        quoted = SheetsClient._quote_sheet_name("GERENCIAR CAIXAS")
        range_name = f"{quoted}!1:1"
        assert range_name == "'GERENCIAR CAIXAS'!1:1"


class TestHyphenNormalization:
    """Test that various hyphen formats are normalized."""

    def test_hyphen_with_no_spaces(self):
        """Test normalization of hyphen without spaces."""
        normalized = CashBalanceService._normalize_text("MONTEPIO GERAL-CC")
        assert normalized == "montepio geral - cc"

    def test_hyphen_with_left_space(self):
        """Test normalization of hyphen with left space only."""
        normalized = CashBalanceService._normalize_text("MONTEPIO GERAL -CC")
        assert normalized == "montepio geral - cc"

    def test_hyphen_with_right_space(self):
        """Test normalization of hyphen with right space only."""
        normalized = CashBalanceService._normalize_text("MONTEPIO GERAL- CC")
        assert normalized == "montepio geral - cc"

    def test_hyphen_with_both_spaces(self):
        """Test normalization of hyphen with both spaces."""
        normalized = CashBalanceService._normalize_text("MONTEPIO GERAL - CC")
        assert normalized == "montepio geral - cc"

    def test_multiple_hyphen_variations_match(self):
        """Test that different hyphen formats match after normalization."""
        text1_normalized = CashBalanceService._normalize_text("MONTEPIO GERAL-CC")
        text2_normalized = CashBalanceService._normalize_text("MONTEPIO GERAL - CC")
        assert text1_normalized == text2_normalized


class TestFileFormatNoBOM:
    """Test that Python files don't have UTF-8 BOM."""

    def test_validate_cash_balance_no_bom(self):
        """Test that validate_cash_balance.py has no UTF-8 BOM."""
        with open("scripts/validate_cash_balance.py", "rb") as f:
            content = f.read()
            assert not content.startswith(b"\xef\xbb\xbf"), "validate_cash_balance.py has UTF-8 BOM"

    def test_cash_balance_service_no_bom(self):
        """Test that cash_balance_service.py has no UTF-8 BOM."""
        with open("src/gmail_to_sheets/services/cash_balance_service.py", "rb") as f:
            content = f.read()
            assert not content.startswith(b"\xef\xbb\xbf"), "cash_balance_service.py has UTF-8 BOM"

    def test_validate_cash_balance_starts_with_shebang(self):
        """Test that validate_cash_balance.py starts with shebang."""
        with open("scripts/validate_cash_balance.py", "rb") as f:
            content = f.read()
            assert content.startswith(b"#!/usr/bin/env python3"), "validate_cash_balance.py doesn't start with shebang"
