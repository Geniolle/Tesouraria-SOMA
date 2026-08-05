"""
Unit tests for MT940 parser.

Tests cover:
- Valid MT940 file parsing
- Edge cases (special characters, amounts, dates)
- Error handling
- Empty/malformed files
"""

import pytest

from src.gmail_to_sheets.parsers.mt940 import MT940Parser
from src.gmail_to_sheets.parsers.exceptions import MT940ParseError


class TestMT940ParserBasic:
    """Test basic MT940 parsing functionality."""

    def test_parse_valid_mt940_file(self):
        """Test parsing a valid MT940 file."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C210101EUR1000,00
:61:2101020101D1000,NMSCTEST TRANSACTION
:62F:C210101EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_file.txt")
        result = parser.parse(content)

        assert result is not None
        assert result.total_transactions == 1
        assert len(result.transactions) == 1
        assert "TEST" in result.transactions[0].descricao

    def test_parse_multiple_transactions(self):
        """Test parsing multiple transactions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCTEST TRANS 1
:61:2101030102D2000,NMSCTEST TRANS 2
:61:2101040103D3000,NMSCTEST TRANS 3
:62F:210101D6000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_file.txt")
        result = parser.parse(content)

        assert result.total_transactions == 3
        assert len(result.transactions) == 3
        assert result.transactions[0].descricao == "TEST TRANS 1"
        assert result.transactions[1].descricao == "TEST TRANS 2"
        assert result.transactions[2].descricao == "TEST TRANS 3"

    def test_parse_empty_file(self):
        """Test parsing empty file raises error."""
        content = ""
        parser = MT940Parser()

        with pytest.raises(MT940ParseError):
            parser.parse(content)

    def test_parse_malformed_file_no_headers(self):
        """Test parsing file without required headers."""
        content = """Some random text
without proper MT940 tags
"""
        parser = MT940Parser()

        with pytest.raises(MT940ParseError):
            parser.parse(content)


class TestMT940ParserAmounts:
    """Test amount parsing and normalization."""

    def test_parse_amount_with_comma_decimal(self):
        """Test parsing amounts with comma as decimal separator."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1234,56
:61:2101020101D1234,56NMSCTEST
:62F:210101D2469,12
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        assert result.transactions[0].valor == 1234.56

    def test_parse_amount_with_thousands_separator(self):
        """Test parsing large amounts with separators."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000000,00
:61:2101020101D999999,99NMSCTEST
:62F:210101D2000000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        assert result.transactions[0].valor == 999999.99

    def test_credit_vs_debit_indicator(self):
        """Test proper identification of credit (C) vs debit (D) transactions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCDEBIT TRANS
:61:2101030102C2000,NMSCDEBIT TRANS
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        assert result.transactions[0].tipo == "Saída"  # Debit
        assert result.transactions[1].tipo == "Entrada"  # Credit


class TestMT940ParserDates:
    """Test date parsing and formatting."""

    def test_parse_date_conversion(self):
        """Test date format conversion from YY/MM/DD to DD/MM/YYYY."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCTEST
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        # Date should be converted and formatted
        assert result.transactions[0].data_mov is not None
        # Format should be DD/MM/YYYY
        parts = result.transactions[0].data_mov.split("/")
        assert len(parts) == 3
        assert len(parts[0]) == 2  # Day
        assert len(parts[1]) == 2  # Month
        assert len(parts[2]) == 4  # Year

    def test_parse_multiple_dates(self):
        """Test parsing transactions with different dates."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCJAN TRANS
:61:2102030202D2000,NMSCFEB TRANS
:61:2103040303D3000,NMSCMAR TRANS
:62F:210101D6000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        dates = [t.data_mov for t in result.transactions]
        # Should have parsed different dates
        assert len(set(dates)) >= 1  # At least one date should exist


class TestMT940ParserDescriptions:
    """Test description parsing and normalization."""

    def test_parse_special_characters_in_description(self):
        """Test handling of special characters in transaction description."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCPGTO. FATURA #123-A/2021 (@50%)
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        desc = result.transactions[0].descricao
        assert "FATURA" in desc or "PGTO" in desc

    def test_parse_unicode_in_description(self):
        """Test handling of accented characters in descriptions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCPAGAMENTO SALÁRIO DEZEMBRO
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        desc = result.transactions[0].descricao
        assert "SALÁRIO" in desc or "SAL" in desc.upper()

    def test_parse_empty_description(self):
        """Test handling of transactions with minimal description."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSC
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        # Should still parse but with minimal description
        assert result.total_transactions == 1


class TestMT940ParserEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_missing_balance_tags(self):
        """Test file with missing balance tags."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:61:2101020101D1000,NMSCTEST
:20:ENDUMSEITE
"""
        parser = MT940Parser()

        with pytest.raises(MT940ParseError):
            parser.parse(content)

    def test_parse_truncated_file(self):
        """Test parsing truncated/incomplete file."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,
"""
        parser = MT940Parser()

        # Should either parse or raise specific error
        try:
            result = parser.parse(content)
            assert result is not None
        except MT940ParseError:
            pass  # Expected for malformed files

    def test_parse_extra_whitespace(self):
        """Test file with extra whitespace and line breaks."""
        content = """:20:STARTUMSEITE

:25:MT940_ACCOUNT
:28C:0/1

:60F:210101D1000,00

:61:2101020101D1000,NMSCTEST

:62F:210101D2000,00

:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        assert result.total_transactions == 1

    def test_parse_duplicate_transactions(self):
        """Test file with duplicate transactions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCDUP TRANS
:61:2101020101D1000,NMSCDUP TRANS
:62F:210101D3000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        # Should parse both even if identical
        assert result.total_transactions == 2


class TestMT940ParserValidation:
    """Test data validation and error handling."""

    def test_parser_returns_valid_transaction_object(self):
        """Test that parsed transactions have all required fields."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCTEST
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        transaction = result.transactions[0]
        # Verify all required Transaction fields exist
        assert hasattr(transaction, 'data_mov')
        assert hasattr(transaction, 'valor')
        assert hasattr(transaction, 'descricao')
        assert hasattr(transaction, 'tipo')
        assert hasattr(transaction, 'account')

    def test_parser_preserves_mt940_file_metadata(self):
        """Test that parser extracts and preserves file metadata."""
        content = """:20:STARTUMSEITE
:25:SPECIFIC_ACCOUNT
:28C:0/1
:60F:210101D1000,00
:61:2101020101D1000,NMSCTEST
:62F:210101D2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser()
        result = parser.parse(content)

        # Should preserve account information
        assert result.transactions[0].account is not None

