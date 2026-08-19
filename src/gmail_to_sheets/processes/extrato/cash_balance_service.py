"""Cash balance service facade."""

from __future__ import annotations

from decimal import Decimal

from src.gmail_to_sheets.processes.extrato.cash_balance_inspector import (
    CashBalanceError,
    CashBalanceInspector,
    HeaderColumn,
)


class CashBalanceService:
    """Public facade for cash balance operations."""

    def __init__(
        self,
        sheets_client,
        spreadsheet_id: str,
        sheet_name: str,
        account_label: str,
        header_row: int = 1,
        row_offset: int = 1,
        verify_after_write: bool = True,
    ) -> None:
        self.inspector = CashBalanceInspector(
            sheets_client=sheets_client,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            account_label=account_label,
            header_row=header_row,
            row_offset=row_offset,
            verify_after_write=verify_after_write,
        )

    def inspect_target(self) -> dict:
        return self.inspector.inspect_target()

    def should_update_balance(self, closing_balance: Decimal, opening_balance: Decimal):
        return self.inspector.should_update_balance(closing_balance, opening_balance)

    def update_balance(self, closing_balance: Decimal) -> dict:
        return self.inspector.update_balance(closing_balance)

    def _load_header_columns(self) -> list[HeaderColumn]:
        return self.inspector.load_header_columns()

    def _find_account_column(self, header_columns: list[HeaderColumn]) -> HeaderColumn:
        return self.inspector.find_account_column(header_columns)

    def _verify_write(self, row_idx: int, col_num: int, expected: Decimal):
        return self.inspector.verify_write(row_idx, col_num, expected)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return CashBalanceInspector.normalize_text(text)

    @staticmethod
    def _row_col_to_a1(row_num: int, col_num: int) -> str:
        return CashBalanceInspector.row_col_to_a1(row_num, col_num)


__all__ = ["CashBalanceError", "CashBalanceService", "HeaderColumn"]
