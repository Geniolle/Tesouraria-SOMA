"""Compatibility wrapper for the extrato cash balance service."""

from src.gmail_to_sheets.processes.extrato.cash_balance_service import (
    CashBalanceError,
    CashBalanceService,
    HeaderColumn,
)

__all__ = ["CashBalanceError", "CashBalanceService", "HeaderColumn"]
