"""Compatibility wrapper for the extrato transaction recovery service."""

from src.gmail_to_sheets.processes.extrato.transaction_recovery_service import (
    TransactionRecoveryService,
)

__all__ = ["TransactionRecoveryService"]
