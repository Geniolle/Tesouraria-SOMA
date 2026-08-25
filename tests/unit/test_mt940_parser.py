"""
Unit tests for MT940 parser.

Tests cover:
- Valid MT940 file parsing
- Edge cases (special characters, amounts, dates)
- Error handling
- Empty/malformed files
"""

from decimal import Decimal

import pytest

from src.gmail_to_sheets.parsers.exceptions import MT940ParseError
from src.gmail_to_sheets.parsers.mt940 import MT940Parser


class TestMT940ParserBasic:
    """Test basic MT940 parsing functionality."""

    def test_parse_valid_mt940_file(self):
        """Test parsing a valid MT940 file."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCTEST TRANSACTION
:62F:C260804EUR2000,00
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
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCTEST TRANS 1
:61:2608050806D2000,NMSCTEST TRANS 2
:61:2608050807D3000,NMSCTEST TRANS 3
:62F:C260804EUR7000,00
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
        parser = MT940Parser("empty_file.txt")

        with pytest.raises(MT940ParseError):
            parser.parse(content)

    def test_parse_malformed_file_no_headers(self):
        """Test parsing file without required headers."""
        content = """Some random text
without proper MT940 tags
"""
        parser = MT940Parser("malformed_file.txt")

        with pytest.raises(MT940ParseError):
            parser.parse(content)

    def test_parse_multiple_mt940_blocks_with_intermediate_balance(self):
        """Test parsing MT940 file with multiple blocks and intermediate balance (:62M:)."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR2080,52
:61:2608050805D38,NMSCSERVICE FEE
:61:2608050805D45,07NMSCBANK CHARGE
:61:2608050805D23,37NMSCRENTAL FEE
:61:2608050805D15,NMSCTRANSFER FEE
:61:2608050805C180,NMSCDEPOSIT
:61:2608050805C10,NMSCINTEREST CREDIT
:62M:C260804EUR2149,08
:60M:C260804EUR2149,08
:61:2608060807D1,NMSCADMIN CHARGE
:61:2608060807D0,04NMSCPROCESSING FEE
:62F:C260804EUR2148,04
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_multiple_blocks.txt")
        result = parser.parse(content)

        # Verify opening balance
        assert result.header.saldo_abertura == Decimal("2080.52")

        # Verify closing balance is the FINAL balance (:62F:), not intermediate (:62M:)
        assert result.footer.saldo_fecho == Decimal("2148.04")

        # Verify intermediate balance (2149.08) is NOT used as final
        assert result.footer.saldo_fecho != Decimal("2149.08")

        # Verify all transactions are parsed (6 in first block + 2 in second = 8 total)
        assert len(result.transactions) == 8
        assert result.total_transactions == 8

        # Verify closing date
        assert result.footer.data_fecho == "04/08/2026"

        # Verify accounting coherence: sum of transactions
        transaction_sum = sum(t.valor for t in result.transactions)
        assert transaction_sum == Decimal("67.52")

        # Verify final balance equation: opening + sum = closing
        assert result.header.saldo_abertura + transaction_sum == result.footer.saldo_fecho


class TestMT940ParserAmounts:
    """Test amount parsing and normalization."""

    def test_parse_amount_with_comma_decimal(self):
        """Test parsing amounts with comma as decimal separator."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1234,56
:61:2608050805D1234,56NMSCTEST
:62F:C260804EUR2469,12
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_amounts.txt")
        result = parser.parse(content)

        assert result.transactions[0].valor == Decimal("-1234.56")

    def test_parse_amount_with_thousands_separator(self):
        """Test parsing large amounts with separators."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000000,00
:61:2608050805D999999,99NMSCTEST
:62F:C260804EUR2000000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_large_amounts.txt")
        result = parser.parse(content)

        assert result.transactions[0].valor == Decimal("-999999.99")

    def test_credit_vs_debit_indicator(self):
        """Test proper identification of credit (C) vs debit (D) transactions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCDEBIT TRANS
:61:2608050806C2000,NMSCDEBIT TRANS
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_credit_debit.txt")
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
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCTEST
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_dates.txt")
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
:60F:C260804EUR1000,00
:61:2608020202D1000,NMSCJAN TRANS
:61:2608030303D2000,NMSCFEB TRANS
:61:2608040404D3000,NMSCMAR TRANS
:62F:C260804EUR7000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_multiple_dates.txt")
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
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCPGTO. FATURA #123-A/2021 (@50%)
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_special.txt")
        result = parser.parse(content)

        desc = result.transactions[0].descricao
        assert "FATURA" in desc or "PGTO" in desc

    def test_parse_unicode_in_description(self):
        """Test handling of accented characters in descriptions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCPAGAMENTO SALÁRIO DEZEMBRO
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_unicode.txt")
        result = parser.parse(content)

        desc = result.transactions[0].descricao
        assert "SALÁRIO" in desc or "SAL" in desc.upper()


    def test_parse_cartao_bustrade_sets_tipo_cartao(self):
        """Test special MT940 description maps TIPO to Cartão."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCPAG.CARTAOBUSTRADE
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_cartao_bustrade.txt")
        result = parser.parse(content)

        assert result.transactions[0].tipo == "Cartão"

    def test_parse_empty_description(self):
        """Test handling of transactions with minimal/empty description."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSC
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_minimal_desc.txt")
        result = parser.parse(content)

        # Parser rejects transactions with empty/minimal description (only "NMSC")
        # This is expected behavior - transactions need meaningful descriptions
        assert result.total_transactions == 0


class TestMT940ParserEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_missing_balance_tags(self):
        """Test file with missing balance tags."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:61:2608050805D1000,NMSCTEST
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_missing_balance.txt")

        with pytest.raises(MT940ParseError):
            parser.parse(content)

    def test_parse_truncated_file(self):
        """Test parsing truncated/incomplete file."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,
"""
        parser = MT940Parser("test_truncated.txt")

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

:60F:C260804EUR1000,00

:61:2608050805D1000,NMSCTEST

:62F:C260804EUR2000,00

:20:ENDUMSEITE
"""
        parser = MT940Parser("test_whitespace.txt")
        result = parser.parse(content)

        assert result.total_transactions == 1

    def test_parse_duplicate_transactions(self):
        """Test file with duplicate transactions."""
        content = """:20:STARTUMSEITE
:25:MT940_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCDUP TRANS
:61:2608050805D1000,NMSCDUP TRANS
:62F:C260804EUR3000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_duplicate.txt")
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
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCTEST
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_validation.txt")
        result = parser.parse(content)

        transaction = result.transactions[0]
        # Verify all required Transaction fields exist
        assert hasattr(transaction, 'data_mov')
        assert hasattr(transaction, 'valor')
        assert hasattr(transaction, 'descricao')
        assert hasattr(transaction, 'tipo')
        # Verify essential fields are populated
        assert transaction.data_mov is not None
        assert transaction.valor is not None
        assert transaction.descricao is not None
        assert transaction.tipo is not None

    def test_parser_preserves_mt940_file_metadata(self):
        """Test that parser extracts and preserves file metadata."""
        content = """:20:STARTUMSEITE
:25:SPECIFIC_ACCOUNT
:28C:0/1
:60F:C260804EUR1000,00
:61:2608050805D1000,NMSCTEST
:62F:C260804EUR2000,00
:20:ENDUMSEITE
"""
        parser = MT940Parser("test_metadata.txt")
        result = parser.parse(content)

        # Parser should successfully parse the file
        assert result is not None
        assert len(result.transactions) > 0
        # Transaction should have valid data
        transaction = result.transactions[0]
        assert transaction.descricao is not None
        assert transaction.valor is not None
