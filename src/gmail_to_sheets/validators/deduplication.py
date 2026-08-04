"""
Deduplication Service

Prevents processing of duplicate transactions.
"""

import logging
from typing import Set

from src.gmail_to_sheets.models.transaction import Transaction
from src.gmail_to_sheets.parsers.exceptions import DeduplicationError


logger = logging.getLogger(__name__)


class DeduplicationService:
    """
    Manages deduplication of transactions.

    Uses a composite key: DATA_MOV|DESCRICAO|VALOR
    """

    def __init__(self):
        """Initialize deduplication service."""
        self.seen_keys: Set[str] = set()
        self.duplicates_count = 0

    def add_existing(self, dedup_keys: Set[str]) -> None:
        """
        Register existing transactions from Sheets.

        Args:
            dedup_keys: Set of deduplication keys already in database
        """
        self.seen_keys.update(dedup_keys)
        logger.info(f"Loaded {len(self.seen_keys)} existing deduplication keys")

    def is_duplicate(self, transaction: Transaction) -> bool:
        """
        Check if transaction is a duplicate.

        Args:
            transaction: Transaction to check

        Returns:
            True if duplicate, False otherwise
        """
        key = transaction.dedup_key()
        return key in self.seen_keys

    def register(self, transaction: Transaction) -> None:
        """
        Register a transaction as processed.

        Args:
            transaction: Transaction to register

        Raises:
            DeduplicationError: If transaction is already registered
        """
        key = transaction.dedup_key()

        if key in self.seen_keys:
            self.duplicates_count += 1
            raise DeduplicationError(key)

        self.seen_keys.add(key)
        logger.debug(f"Registered transaction: {key}")

    def batch_register(self, transactions: list[Transaction]) -> int:
        """
        Register multiple transactions.

        Args:
            transactions: List of transactions

        Returns:
            Number of successfully registered transactions
        """
        registered = 0
        for txn in transactions:
            try:
                self.register(txn)
                registered += 1
            except DeduplicationError:
                logger.debug(f"Skipped duplicate: {txn.dedup_key()}")
                self.duplicates_count += 1

        return registered

    def get_stats(self) -> dict:
        """
        Get deduplication statistics.

        Returns:
            Stats dictionary
        """
        return {
            "total_seen": len(self.seen_keys),
            "duplicates_skipped": self.duplicates_count,
        }
