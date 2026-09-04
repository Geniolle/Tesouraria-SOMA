"""
MT940 Parser

Parses MT940 format bank statements into structured transaction data.
Handles multiple SWIFT blocks and various date formats.
"""

import logging
import unicodedata
from decimal import Decimal
from typing import Optional

from src.gmail_to_sheets.models.transaction import (
    MT940File,
    MT940Footer,
    MT940Header,
    Transaction,
)
from src.gmail_to_sheets.parsers.exceptions import (
    MT940InvalidAmount,
    MT940InvalidDate,
    MT940InvalidFormat,
    MT940MissingSection,
    MT940ParseError,
)

logger = logging.getLogger(__name__)


class MT940Parser:
    """Parser for MT940 bank statement format."""

    def __init__(self, filename: str):
        """Initialize parser."""
        self.filename = filename

    def parse(self, content: str) -> MT940File:
        """
        Parse MT940 file content.

        Args:
            content: Raw file content as string

        Returns:
            Parsed MT940File with transactions

        Raises:
            MT940ParseError: If parsing fails
        """
        try:
            logger.info(f"Parsing {self.filename}")

            # Extract all lines
            lines = [line.strip() for line in content.split("\n") if line.strip()]

            # Parse header, transactions, and footer
            header = self._parse_header(lines)
            transactions = self._parse_transactions(lines)
            footer = self._parse_footer(lines)

            mt940_file = MT940File(
                filename=self.filename,
                header=header,
                transactions=transactions,
                footer=footer,
            )

            logger.info(
                f"Successfully parsed {self.filename}: "
                f"{len(transactions)} transactions"
            )

            return mt940_file
        except MT940ParseError:
            raise
        except Exception as e:
            raise MT940ParseError(
                f"Failed to parse {self.filename}: {e}"
            ) from e

    def _parse_header(self, lines: list[str]) -> MT940Header:
        """Parse opening balance section."""
        for line in lines:
            if line.startswith(":60F:") or line.startswith(":60M:"):
                return self._parse_opening_balance(line)

        raise MT940MissingSection("opening balance (:60F: or :60M:)")

    def _parse_opening_balance(self, line: str) -> MT940Header:
        """
        Parse opening balance line.

        Format: :60[FM]:C/DYYMMDDEUR<amount>
        Example: :60F:C260801EUR1823,21
        Position: 0-4:tag, 5:C/D, 6-11:YYMMDD, 12-14:EUR, 15+:amount
        """
        try:
            if len(line) < 15:
                raise MT940InvalidFormat(f"Opening balance line too short: {line}")

            date_part = line[6:12]
            amount_part = line[15:]

            data_mov = self._format_date_mt940(date_part)
            saldo = self._parse_amount(amount_part)

            logger.debug(f"Opening balance: {data_mov}, {saldo}")

            return MT940Header(data_mov=data_mov, saldo_abertura=saldo)
        except (MT940ParseError, ValueError, IndexError) as e:
            raise MT940ParseError(f"Failed to parse opening balance: {e}") from e

    def _parse_transactions(self, lines: list[str]) -> list[Transaction]:
        """Parse all transaction lines."""
        transactions = []
        current_date = None

        for line in lines:
            # Track opening balance date for context
            if line.startswith(":60F:") or line.startswith(":60M:"):
                try:
                    current_date = self._extract_date_from_line(line, 6)
                except Exception:
                    pass
                continue

            # Parse transactions
            if line.startswith(":61:"):
                try:
                    txn = self._parse_transaction_line(line, current_date)
                    if txn:
                        transactions.append(txn)
                except Exception as e:
                    logger.debug(f"Failed to parse transaction: {line} ({e})")
                    continue

        logger.info(f"Parsed {len(transactions)} transactions")
        return transactions

    def _parse_transaction_line(
        self, line: str, data_mov: Optional[str]
    ) -> Optional[Transaction]:
        """
        Parse single transaction line.

        Format: :61:YYMMDDVVMMDD[D|C]Amount NMSC Description...
        Example: :61:2608010801D1,NMSCEMISSAO EXTR. CONTA-2026-07-31
        """
        try:
            # Remove tag (:61: is 4 chars, so remove first 4)
            content = line[4:]

            # Extract movement date (YYMMDD at position 0-6)
            if len(content) < 6:
                return None

            date_part = content[0:6]
            data_mov_txn = self._format_date_mt940(date_part)

            # Extract credit/debit indicator (position 14)
            # Format: YYMMDD(0-5) MMDD(6-9) D/C(10) Amount...
            # But content already has tag removed, so:
            # YYMMDD(0-5) MMDD(6-9) D/C(10) Amount(11+) NMSC...
            if len(content) < 11:
                return None

            dc_indicator = content[10]
            is_credit = dc_indicator == "C"
            # Extract amount (after position 10, before NMSC)
            nmsc_index = content.find("NMSC")
            if nmsc_index <= 11:
                return None

            amount_str = content[11:nmsc_index].strip()

            # Parse amount (handle decimal separators)
            valor = self._parse_amount(amount_str)
            if not is_credit:
                valor = -valor

            # Extract description (after NMSC)
            descricao = content[nmsc_index + 4:].strip()
            # Remove slashes and clean
            descricao = descricao.replace("/", "").strip()

            if not descricao:
                return None

            tipo = self._resolve_transaction_type(descricao, is_credit)

            transaction = Transaction(
                data_mov=data_mov_txn,
                data_valor=data_mov_txn,
                descricao=descricao,
                valor=valor,
                tipo=tipo,
            )

            logger.debug(f"Parsed: {descricao} {valor}")
            return transaction

        except Exception as e:
            logger.debug(f"Error parsing transaction: {e}")
            return None

    def _resolve_transaction_type(self, descricao: str, is_credit: bool) -> str:
        """Resolve transaction type for MT940 rows."""
        descricao_norm = descricao.replace("/", "").strip().upper()
        if descricao_norm == "PAG.CARTAOBUSTRADE":
            return "Cartão"

        # Cash/cheque deposits ("ENT.NUMERARIO") represent internal transfers
        # e.g.: "ENT.NUMERARIO  CH24 0006774253"
        normalized = unicodedata.normalize("NFD", descricao_norm)
        ascii_text = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        compact = "".join(ascii_text.split())
        if "ENT.NUMERARIO" in compact or "ENTNUMERARIO" in compact:
            return "Transferência"

        return "Entrada" if is_credit else "Saída"

    def _parse_footer(self, lines: list[str]) -> MT940Footer:
        """Parse closing balance section (final balance from end of file)."""
        for line in reversed(lines):
            if line.startswith(":62F:") or line.startswith(":62M:"):
                return self._parse_closing_balance(line)

        raise MT940MissingSection("closing balance (:62F: or :62M:)")

    def _parse_closing_balance(self, line: str) -> MT940Footer:
        """
        Parse closing balance line.

        Format: :62[FM]:C/DYYMMDDEUR<amount>
        Position: 0-4:tag, 5:C/D, 6-11:YYMMDD, 12-14:EUR, 15+:amount
        """
        try:
            date_part = line[6:12]
            amount_part = line[15:]

            data_fecho = self._format_date_mt940(date_part)
            saldo = self._parse_amount(amount_part)

            logger.debug(f"Closing balance: {data_fecho}, {saldo}")

            return MT940Footer(data_fecho=data_fecho, saldo_fecho=saldo)
        except (MT940ParseError, ValueError, IndexError) as e:
            raise MT940ParseError(f"Failed to parse closing balance: {e}") from e

    def _format_date_mt940(self, date_yymmdd: str) -> str:
        """Convert MT940 date format (YYMMDD) to DD/MM/YYYY."""
        date_yymmdd = date_yymmdd.strip()
        if len(date_yymmdd) != 6 or not date_yymmdd.isdigit():
            raise MT940InvalidDate(date_yymmdd, "YYMMDD")

        yy = int(date_yymmdd[0:2])
        mm = int(date_yymmdd[2:4])
        dd = int(date_yymmdd[4:6])

        yyyy = 2000 + yy if yy < 50 else 1900 + yy

        if not (1 <= mm <= 12):
            raise MT940InvalidDate(date_yymmdd, "month")
        if not (1 <= dd <= 31):
            raise MT940InvalidDate(date_yymmdd, "day")

        return f"{dd:02d}/{mm:02d}/{yyyy}"

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string (comma as decimal separator)."""
        if not amount_str:
            raise MT940InvalidAmount(amount_str)

        try:
            # Clean: remove trailing commas and spaces
            amount_str = amount_str.strip().rstrip(",")

            if not amount_str or amount_str == "":
                raise MT940InvalidAmount(amount_str)

            # Normalize: replace comma with dot
            normalized = amount_str.replace(",", ".")
            return Decimal(normalized)
        except Exception as e:
            raise MT940InvalidAmount(amount_str) from e

    def _extract_date_from_line(self, line: str, position: int) -> str:
        """Extract and format date from line at position."""
        date_part = line[position : position + 6]
        return self._format_date_mt940(date_part)
