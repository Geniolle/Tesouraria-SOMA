"""
Balance Protection Service

Prevents stale cash balance regression when processing historical MT940 files.

Rules:
1. Current balance == opening balance of file: safe to update to closing
2. Current balance == closing balance of file: idempotent (no change)
3. Current balance > closing balance of file: file is historical, skip update (backfill mode)
4. Current balance incompatible: raise error (data inconsistency)

Uses internalDate of Gmail message to detect historical processing.
"""

import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


class BalanceProtectionService:
    """Protect cash balance from regression during processing."""

    class BalanceDecision:
        """Result of balance safety check."""

        def __init__(
            self,
            should_update: bool,
            reason: str,
            is_historical: bool = False,
            new_value: Optional[Decimal] = None,
        ):
            self.should_update = should_update
            self.reason = reason
            self.is_historical = is_historical
            self.new_value = new_value

    @staticmethod
    def decide_balance_update(
        current_balance: Decimal,
        file_opening: Decimal,
        file_closing: Decimal,
        message_internal_date_ms: Optional[int] = None,
        processed_messages: Optional[list[tuple[int, Decimal]]] = None,
    ) -> "BalanceProtectionService.BalanceDecision":
        """
        Decide whether it's safe to update balance.

        Args:
            current_balance: Current balance in GERENCIAR CAIXAS!C2 (as Decimal)
            file_opening: Opening balance in MT940 file (saldo_abertura)
            file_closing: Closing balance in MT940 file (saldo_fecho)
            message_internal_date_ms: Gmail internalDate (milliseconds since epoch),
                                      used to detect historical messages
            processed_messages: List of (internalDate_ms, balance) tuples already
                               processed, for chronological checks

        Returns:
            BalanceDecision with should_update flag and reason
        """
        logger.info("=" * 80)
        logger.info("BALANCE SAFETY CHECK")
        logger.info("=" * 80)
        logger.info(f"Current balance: {current_balance}")
        logger.info(f"File opening: {file_opening}")
        logger.info(f"File closing: {file_closing}")

        # Quantize for comparison (allow 0.01 tolerance)
        current = current_balance.quantize(Decimal("0.01"))
        opening = file_opening.quantize(Decimal("0.01"))
        closing = file_closing.quantize(Decimal("0.01"))

        # Case 1: Current == Closing
        # This file's results are already applied (idempotent)
        if current == closing:
            logger.info("✓ Current balance == file closing: Idempotent (no change needed)")
            return BalanceProtectionService.BalanceDecision(
                should_update=False,
                reason="Idempotent: balance already at file closing",
                new_value=closing,
            )

        # Case 2: Current == Opening
        # Safe to advance to closing
        if current == opening:
            logger.info("✓ Current balance == file opening: Safe to update to closing")
            return BalanceProtectionService.BalanceDecision(
                should_update=True,
                reason="Current equals opening, safe to advance to closing",
                new_value=closing,
            )

        # Case 3: Current > Closing
        # File is historical (older than current processed file)
        # Don't regress the balance
        if current > closing:
            logger.warning(
                f"⚠ Current ({current}) > File closing ({closing}): "
                f"File is historical, skipping balance update"
            )
            return BalanceProtectionService.BalanceDecision(
                should_update=False,
                reason="File is historical (current balance higher than file closing)",
                is_historical=True,
                new_value=current,
            )

        # Case 4: Current < Opening
        # Current is lower than this file's opening
        # This shouldn't happen in normal flow (would mean balances went backwards)
        logger.error(
            f"✗ Current ({current}) < File opening ({opening}): "
            f"Balance inconsistency detected"
        )
        return BalanceProtectionService.BalanceDecision(
            should_update=False,
            reason="Balance inconsistency: current is below file opening",
            new_value=current,
        )

    @staticmethod
    def is_message_historical(
        message_internal_date_ms: int,
        processed_messages: Optional[list[tuple[int, Decimal]]] = None,
    ) -> bool:
        """
        Detect if message is older than previously processed messages.

        Args:
            message_internal_date_ms: Gmail internalDate in milliseconds
            processed_messages: List of (internalDate_ms, balance) tuples

        Returns:
            True if this message is older than recent processed messages
        """
        if not processed_messages:
            return False

        for prev_date_ms, _ in processed_messages:
            if message_internal_date_ms < prev_date_ms:
                return True

        return False
