"""
Orchestrator: Coordinates the Gmail-to-Sheets pipeline.

Complete end-to-end flow:
1. Load configuration
2. Authenticate Gmail (OAuth) and Sheets (Service account)
3. Search for MT940 emails
4. Download and parse attachments
5. Load existing transactions (deduplication)
6. Write to Google Sheets with formatting
7. Transfer to CONTAORDEM sheet
"""

import logging

from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.exceptions.application import AuthenticationError
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.services.cash_balance_service import CashBalanceService
from src.gmail_to_sheets.services.sheets_writer import SheetsWriter
from src.gmail_to_sheets.services.smart_deduplication_service import SmartDeduplicationService
from src.gmail_to_sheets.services.transaction_recovery_service import (
    TransactionRecoveryService,
)
from src.gmail_to_sheets.services.transfer_matching_service import TransferMatchingService
from src.gmail_to_sheets.services.transfer_service import TransferService

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main flow controller for the gmail-to-sheets pipeline."""

    def __init__(self) -> None:
        """Initialize the orchestrator."""
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.gmail_client: GmailClient | None = None
        self.sheets_writer: SheetsWriter | None = None
        self.sheets_client: SheetsClient | None = None

    def run(self) -> None:
        """Execute the complete pipeline."""
        try:
            logger.info("=" * 80)
            logger.info("Starting gmail-to-sheets pipeline")
            logger.info("=" * 80)

            # Phase 1: Load configuration
            logger.info(f"[1/7] Configuration loaded: {self.settings.gmail.account_email}")

            # Phase 2: Authenticate Gmail
            self._authenticate_gmail()

            # Phase 3: Authenticate Sheets
            self._authenticate_sheets()

            # Phase 4: Search Gmail
            message_ids = self._search_messages()
            if not message_ids:
                logger.warning("No emails found matching criteria")
                return

            # Select the most recent message by internalDate (not by search order)
            message_id = self._select_latest_message(message_ids)

            # Phase 5: Download and parse
            mt940_file = self._download_and_parse(message_id)
            if not mt940_file or not mt940_file.transactions:
                logger.warning("No transactions found in attachment")
                return

            # Phase 5.5: Validate accounting reconciliation
            self._validate_mt940_reconciliation(mt940_file)

            # Phase 6: Smart deduplication (by date + value)
            # MUST check T_EXTRATO, not CONTAORDEM, since SheetsWriter writes to T_EXTRATO
            dedup = SmartDeduplicationService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                target_sheet="T_EXTRATO"
            )
            logger.info("      Using smart deduplication (checking T_EXTRATO)")

            # Phase 6.5: Recover existing transaction IDs (for partial execution recovery)
            logger.info("[6.25/7] Attempting to recover existing transaction IDs...")
            recovery = TransactionRecoveryService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                source_sheet="T_EXTRATO",
            )
            recovered_ids = recovery.recover_batch(mt940_file)
            if recovered_ids:
                logger.info(f"      Recovered {len(recovered_ids)} existing IDs from T_EXTRATO")

            # Phase 6.75: Write to Sheets
            result = self._write_to_sheets(mt940_file, dedup)
            written_ids = result.get("written_ids", [])

            # Combine recovered IDs with newly written IDs for transfer
            all_ids = recovered_ids + written_ids
            logger.info(
                f"      Total IDs for transfer: {len(all_ids)} "
                f"(recovered: {len(recovered_ids)}, new: {len(written_ids)})"
            )

            # Phase 7: Transfer + Matching (Integrated Batch)
            logger.info("[7/7] Transferring to CONTAORDEM with matching...")
            if self.settings.enable_matching:
                transfer_result = self._transfer_with_matching(all_ids)
            else:
                transfer_result = self._transfer_to_contaordem(all_ids)

            # Phase 8: Update cash balance (with safety checks)
            cash_balance_result = None
            if self.settings.cash_balance.update_enabled:
                cash_balance_result = self._update_cash_balance(
                    mt940_file.footer.saldo_fecho,
                    mt940_file.header.saldo_abertura,
                )

            # Phase 9: Archive email to backup folder
            if self.settings.archive_after_process:
                self._archive_email(message_id)

            logger.info("=" * 80)
            logger.info("Pipeline completed successfully!")
            logger.info(f"  - Transactions written: {result['written']}")
            logger.info(f"  - Recovered from existing: {len(recovered_ids)}")
            logger.info(f"  - Duplicates skipped: {result['skipped']}")
            logger.info(f"  - Transferred to CONTAORDEM: {transfer_result['transferred']}")
            logger.info(f"  - Already existing: {transfer_result['already_exists']}")
            if self.settings.enable_matching:
                logger.info(f"  - Matched with CONSTANTES: {transfer_result.get('matched', 0)}")
                logger.info(f"  - No match found: {transfer_result.get('no_match', 0)}")
            if cash_balance_result:
                if isinstance(cash_balance_result, dict):
                    if cash_balance_result.get("skipped"):
                        logger.info(f"  - Cash balance: {cash_balance_result['reason']}")
                    elif "target_cell" in cash_balance_result:
                        logger.info(f"  - Cash balance updated in {cash_balance_result['target_cell']}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise

    def _authenticate_gmail(self) -> None:
        """Authenticate with Gmail API."""
        try:
            logger.info("[2/7] Authenticating with Gmail API...")
            authenticator = GmailAuthenticator(
                client_secrets_path=self.settings.gmail.client_secrets_path,
                credentials_path=self.settings.gmail.credentials_path,
            )
            credentials = authenticator.get_credentials()
            self.gmail_client = GmailClient(credentials)
            logger.info("      Gmail authenticated")
        except Exception as e:
            logger.error(f"Gmail authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with Gmail: {e}") from e

    def _authenticate_sheets(self) -> None:
        """Authenticate with Google Sheets API."""
        try:
            logger.info("[3/7] Authenticating with Google Sheets...")
            self.sheets_client = SheetsClient(
                service_account_path=self.settings.sheets.service_account_path
            )
            self.sheets_writer = SheetsWriter(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                sheet_name=self.settings.sheets.sheet_name,
            )
            logger.info("      Sheets authenticated")
        except Exception as e:
            logger.error(f"Sheets authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with Sheets: {e}") from e

    def _search_messages(self) -> list[str]:
        """Search for messages matching criteria."""
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")

        try:
            logger.info("[4/7] Searching Gmail for MT940 attachments...")
            message_ids = self.gmail_client.search_messages(
                query=self.settings.gmail.search_query,
                max_results=self.settings.batch_size,
            )
            logger.info(f"      Found {len(message_ids)} email(s)")
            return message_ids
        except Exception as e:
            logger.error(f"Message search failed: {e}")
            raise

    def _select_latest_message(self, message_ids: list[str]) -> str:
        """
        Select the most recent message by internalDate.

        Does not rely on search result ordering (which is not guaranteed).
        Fetches metadata for each message and selects the one with the
        highest internalDate timestamp.

        Args:
            message_ids: List of Gmail message IDs

        Returns:
            The message ID with the latest internalDate

        Raises:
            ValueError: If no valid message found
        """
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")

        if not message_ids:
            raise ValueError("No messages to select from")

        try:
            logger.info(f"      Selecting latest from {len(message_ids)} message(s)...")

            # Fetch metadata for all messages
            messages = []
            for msg_id in message_ids:
                try:
                    msg = self.gmail_client.get_message(msg_id)
                    internal_date = msg.get("internalDate")
                    if internal_date:
                        messages.append((msg_id, int(internal_date)))
                    else:
                        logger.warning(f"Message {msg_id} has no internalDate")
                except Exception as e:
                    logger.warning(f"Failed to get metadata for {msg_id}: {e}")

            if not messages:
                raise ValueError(
                    f"No messages with valid internalDate found (checked {len(message_ids)})"
                )

            # Select message with highest internalDate
            selected_id, selected_date = max(messages, key=lambda x: x[1])

            logger.info(f"      Selected message: {selected_id}")
            logger.info(f"      internalDate: {selected_date}")
            logger.info(f"      Total messages with valid dates: {len(messages)}")

            return selected_id

        except Exception as e:
            logger.error(f"Failed to select latest message: {e}")
            raise

    def _validate_mt940_reconciliation(self, mt940_file) -> dict:
        """Validate accounting reconciliation of MT940 file."""
        from decimal import Decimal

        try:
            logger.info("[5.5/7] Validating MT940 reconciliation...")

            opening_balance = mt940_file.header.saldo_abertura
            closing_balance = mt940_file.footer.saldo_fecho
            transaction_total = sum(
                (transaction.valor for transaction in mt940_file.transactions),
                Decimal("0.00"),
            )

            calculated_balance = opening_balance + transaction_total
            difference = (closing_balance - calculated_balance).quantize(Decimal("0.01"))

            logger.info(f"      Opening balance: {opening_balance}")
            logger.info(f"      Transaction sum: {transaction_total}")
            logger.info(f"      Closing balance: {closing_balance}")
            logger.info(f"      Difference: {difference}")

            if abs(difference) > Decimal("0.01"):
                raise ValueError(
                    f"Reconciliation failed: opening ({opening_balance}) + "
                    f"transactions ({transaction_total}) = calculated ({calculated_balance}), "
                    f"but closing is {closing_balance} (difference: {difference})"
                )

            logger.info("      ✓ Reconciliation validated")
            return {
                "opening_balance": opening_balance,
                "transaction_total": transaction_total,
                "closing_balance": closing_balance,
                "calculated_balance": calculated_balance,
                "difference": difference,
            }

        except Exception as e:
            logger.error(f"Reconciliation validation failed: {e}")
            raise

    def _download_and_parse(self, message_id: str):
        """Download and parse MT940 attachment."""
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")

        try:
            logger.info("[5/7] Downloading and parsing MT940...")
            attachments = self.gmail_client.get_attachments(message_id)

            if not attachments:
                logger.warning("No .txt attachments found")
                return None

            processor = AttachmentProcessor(self.gmail_client)
            mt940_file = processor.process_attachment(
                message_id=message_id,
                attachment_id=attachments[0].get("attachment_id"),
                filename=attachments[0]["filename"],
            )

            logger.info(f"      Parsed {mt940_file.total_transactions} transactions")
            return mt940_file

        except Exception as e:
            logger.error(f"Parse failed: {e}")
            raise

    def _write_to_sheets(self, mt940_file, dedup) -> dict:
        """Write transactions to Google Sheets."""
        if not self.sheets_writer:
            raise RuntimeError("Sheets writer not initialized")

        try:
            logger.info("[6.75/7] Writing to Google Sheets...")
            result = self.sheets_writer.write_transactions(
                transactions=mt940_file.transactions,
                opening_balance=str(mt940_file.header.saldo_abertura),
                dedup_service=dedup,
            )
            logger.info(f"      Wrote {result['written']} transaction(s)")
            return result

        except Exception as e:
            logger.error(f"Write failed: {e}")
            raise

    def _transfer_to_contaordem(self, source_ids: list[str] | None = None) -> dict:
        """Transfer pending transactions to CONTAORDEM sheet."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("[7/7] Transferring to CONTAORDEM sheet...")
            transfer = TransferService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                source_sheet="T_EXTRATO",
                target_sheet="CONTAORDEM",
            )
            result = transfer.transfer_pending(source_ids=source_ids)
            logger.info(f"      Transferred {result['transferred']} transaction(s)")
            return result

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            raise

    def _transfer_with_matching(self, source_ids: list[str] | None = None) -> dict:
        """Transfer to CONTAORDEM with integrated matching (batch optimized)."""
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            logger.info("      Using integrated transfer+matching (batch optimized)...")
            service = TransferMatchingService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                source_sheet="T_EXTRATO",
                target_sheet="CONTAORDEM",
                reference_sheet="CONSTANTES",
            )
            result = service.process_with_matching(source_ids=source_ids)
            logger.info(f"      Transferred: {result['transferred']}")
            logger.info(f"      Matched: {result.get('matched', 0)}")
            return result

        except Exception as e:
            logger.error(f"Transfer+matching failed: {e}")
            raise

    def _update_cash_balance(self, closing_balance, opening_balance) -> dict:
        """
        Update cash balance in GERENCIAR CAIXAS sheet with safety checks.

        Prevents regressing the balance when processing historical MT940 files.
        """
        if not self.sheets_client:
            raise RuntimeError("Sheets client not initialized")

        try:
            from decimal import Decimal

            logger.info("[8/8] Checking balance safety...")
            cash_service = CashBalanceService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                sheet_name=self.settings.cash_balance.sheet_name,
                account_label=self.settings.cash_balance.account_label,
                header_row=self.settings.cash_balance.header_row,
                row_offset=self.settings.cash_balance.row_offset,
                verify_after_write=self.settings.cash_balance.verify_after_write,
            )

            # Check if safe to update
            decision = cash_service.should_update_balance(
                closing_balance=Decimal(str(closing_balance)),
                opening_balance=Decimal(str(opening_balance)),
            )

            if not decision.should_update:
                logger.info(f"      Balance update skipped: {decision.reason}")
                if decision.is_historical:
                    logger.info("      (This is a historical/backfill file - balance will not regress)")
                return {
                    "skipped": True,
                    "reason": decision.reason,
                    "is_historical": decision.is_historical,
                }

            result = cash_service.update_balance(closing_balance)
            logger.info(f"      Cash balance updated to {result['written_value']}")
            return result

        except Exception as e:
            logger.error(f"Cash balance update failed: {e}")
            raise

    def _archive_email(self, message_id: str) -> None:
        """
        Move email to backup folder after successful processing.

        Combines label addition and INBOX removal in a single atomic operation.
        Errors during archiving must stop the pipeline - if we cannot
        reliably move the email to backup, we must not continue.
        """
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")

        try:
            logger.info("[9/9] Moving email to backup folder...")
            label_id = self.gmail_client.get_or_create_label_id(
                self.settings.gmail.backup_label_name
            )
            logger.info(f"      Resolved label ID: {label_id}")

            # Atomic operation: add backup label and remove INBOX in one call
            self.gmail_client.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={
                    "addLabelIds": [label_id],
                    "removeLabelIds": ["INBOX"],
                },
            ).execute()

            logger.info(f"      Added backup label '{self.settings.gmail.backup_label_name}'")
            logger.info("      Email removed from INBOX")
            logger.info("      Email archived successfully")
        except Exception as e:
            logger.error(f"Failed to archive email: {e}")
            raise

