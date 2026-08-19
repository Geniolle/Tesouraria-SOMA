"""Cash balance inspection helpers."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.services.balance_protection_service import (
    BalanceProtectionService,
)

logger = logging.getLogger(__name__)


class CashBalanceError(Exception):
    """Raised when cash balance operations fail."""


@dataclass(frozen=True)
class HeaderColumn:
    index: int
    column_number: int
    column_letter: str
    original_name: str
    normalized_name: str


class CashBalanceInspector:
    """Encapsulates header discovery and balance verification."""

    def __init__(
        self,
        sheets_client: SheetsClient,
        spreadsheet_id: str,
        sheet_name: str,
        account_label: str,
        header_row: int = 1,
        row_offset: int = 1,
        verify_after_write: bool = True,
    ) -> None:
        self.sheets_client = sheets_client
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.account_label = account_label
        self.header_row = header_row
        self.row_offset = row_offset
        self.verify_after_write = verify_after_write

    def inspect_target(self) -> dict:
        header_columns = self.load_header_columns()
        account_column = self.find_account_column(header_columns)
        target_row = self.header_row + self.row_offset
        label_cell = self.row_col_to_a1(self.header_row, account_column.column_number)
        target_cell = self.row_col_to_a1(target_row, account_column.column_number)
        previous_value = self.sheets_client.get_cell(
            self.spreadsheet_id,
            self.sheet_name,
            target_row,
            account_column.column_number,
        )
        if previous_value is not None:
            previous_value = str(previous_value).strip()

        return {
            "header_row": self.header_row,
            "header_name": account_column.original_name,
            "header_normalized": account_column.normalized_name,
            "header_index": account_column.index,
            "column_number": account_column.column_number,
            "column_letter": account_column.column_letter,
            "label_cell": label_cell,
            "target_cell": target_cell,
            "previous_value": previous_value,
            "written_value": None,
            "verified_value": None,
            "verified": False,
        }

    def should_update_balance(
        self, closing_balance: Decimal, opening_balance: Decimal
    ) -> BalanceProtectionService.BalanceDecision:
        try:
            header_columns = self.load_header_columns()
            account_column = self.find_account_column(header_columns)
            target_row = self.header_row + self.row_offset
            current_value = self.sheets_client.get_cell(
                self.spreadsheet_id,
                self.sheet_name,
                target_row,
                account_column.column_number,
            )
            if current_value is None:
                current_balance = Decimal("0.00")
            else:
                try:
                    if isinstance(current_value, str):
                        current_balance = Decimal(current_value.strip().replace(",", "."))
                    else:
                        current_balance = Decimal(str(current_value))
                except (ValueError, TypeError, InvalidOperation):
                    current_balance = Decimal("0.00")

            return BalanceProtectionService.decide_balance_update(
                current_balance=current_balance,
                file_opening=opening_balance,
                file_closing=closing_balance,
            )
        except Exception as e:
            raise CashBalanceError(f"Failed to check balance safety: {e}") from e

    def update_balance(self, closing_balance: Decimal) -> dict:
        header_columns = self.load_header_columns()
        account_column = self.find_account_column(header_columns)
        target_row = self.header_row + self.row_offset
        label_cell = self.row_col_to_a1(self.header_row, account_column.column_number)
        target_cell = self.row_col_to_a1(target_row, account_column.column_number)
        previous_value = self.sheets_client.get_cell(
            self.spreadsheet_id,
            self.sheet_name,
            target_row,
            account_column.column_number,
        )
        if previous_value is not None:
            previous_value = str(previous_value).strip()

        quantized_balance = closing_balance.quantize(Decimal("0.01"))
        balance_formatted = str(quantized_balance).replace(".", ",")
        api_numeric_value = float(quantized_balance)
        self.sheets_client.update_cell(
            self.spreadsheet_id,
            self.sheet_name,
            target_row,
            account_column.column_number,
            value=api_numeric_value,
            value_input_option="RAW",
        )

        verified_value = None
        verified = False
        if self.verify_after_write:
            verified_value = self.verify_write(target_row, account_column.column_number, closing_balance)
            verified = verified_value is not None
            if not verified:
                raise CashBalanceError(
                    f"Verification failed: wrote {balance_formatted} but read different value"
                )

        return {
            "header_row": self.header_row,
            "header_name": account_column.original_name,
            "header_normalized": account_column.normalized_name,
            "header_index": account_column.index,
            "column_number": account_column.column_number,
            "column_letter": account_column.column_letter,
            "label_cell": label_cell,
            "target_cell": target_cell,
            "previous_value": previous_value,
            "written_value": balance_formatted,
            "verified_value": str(verified_value) if verified_value else None,
            "verified": verified,
        }

    def load_header_columns(self) -> list[HeaderColumn]:
        header_values = self.sheets_client.get_row(self.spreadsheet_id, self.sheet_name, self.header_row)
        if not header_values:
            raise CashBalanceError(f"Header row {self.header_row} is empty in {self.sheet_name}")

        header_columns: list[HeaderColumn] = []
        for index, cell_value in enumerate(header_values):
            if cell_value:
                cell_value_str = str(cell_value).strip()
                if cell_value_str:
                    column_number = index + 1
                    column_letter = self.sheets_client._number_to_column(column_number)
                    header_columns.append(
                        HeaderColumn(
                            index=index,
                            column_number=column_number,
                            column_letter=column_letter,
                            original_name=cell_value_str,
                            normalized_name=self.normalize_text(cell_value_str),
                        )
                    )
        return header_columns

    def find_account_column(self, header_columns: list[HeaderColumn]) -> HeaderColumn:
        normalized_label = self.normalize_text(self.account_label)
        found_columns = [col for col in header_columns if col.normalized_name == normalized_label]
        if len(found_columns) == 0:
            raise CashBalanceError(
                f"Account label '{self.account_label}' not found in {self.sheet_name} header row {self.header_row}"
            )
        if len(found_columns) > 1:
            raise CashBalanceError(
                f"Multiple occurrences ({len(found_columns)}) of account label found in header row"
            )
        return found_columns[0]

    def verify_write(self, row_idx: int, col_num: int, expected: Decimal) -> Optional[Decimal]:
        cell_value = self.sheets_client.get_cell(self.spreadsheet_id, self.sheet_name, row_idx, col_num)
        if not cell_value:
            return None
        try:
            if isinstance(cell_value, str):
                parsed = Decimal(cell_value.strip().replace(",", "."))
            else:
                parsed = Decimal(str(cell_value))
        except Exception:
            return None
        if abs(parsed - expected) <= Decimal("0.01"):
            return parsed
        return None

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        text = " ".join(str(text).split()).casefold()
        text = re.sub(r"\s*-\s*", " - ", text)
        normalized = unicodedata.normalize("NFD", text)
        text_no_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", text_no_accents)

    @staticmethod
    def row_col_to_a1(row_num: int, col_num: int) -> str:
        col_letter = ""
        n = col_num
        while n > 0:
            n -= 1
            col_letter = chr(ord("A") + (n % 26)) + col_letter
            n //= 26
        return f"{col_letter}{row_num}"
