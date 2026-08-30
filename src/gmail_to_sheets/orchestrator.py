"""
Orchestrator for the Extrato pipeline.

The class keeps the pipeline composition in one place, while the heavier
operations live in dedicated helpers and services.
"""

from __future__ import annotations

import logging

from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.exceptions.application import AuthenticationError
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.extrato.cash_balance_service import CashBalanceService
from src.gmail_to_sheets.processes.extrato.pipeline_support import (
    archive_email,
    download_and_parse_attachment,
    select_latest_message,
    validate_mt940_reconciliation,
)
from src.gmail_to_sheets.processes.extrato.sheets_writer import SheetsWriter
from src.gmail_to_sheets.processes.extrato.smart_deduplication_service import (
    SmartDeduplicationService,
)
from src.gmail_to_sheets.processes.extrato.transaction_recovery_service import (
    TransactionRecoveryService,
)
from src.gmail_to_sheets.processes.extrato.transfer_matching_service import (
    TransferMatchingService,
)
from src.gmail_to_sheets.processes.extrato.transfer_service import TransferService

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main flow controller for the gmail-to-sheets pipeline."""

    def __init__(
        self,
        settings=None,
        gmail_client: GmailClient | None = None,
        sheets_client: SheetsClient | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.gmail_client: GmailClient | None = gmail_client
        self.sheets_writer: SheetsWriter | None = None
        self.sheets_client: SheetsClient | None = sheets_client

    def run(self) -> dict:
        """Execute the complete pipeline."""
        try:
            logger.info("=" * 80)
            logger.info("Starting gmail-to-sheets pipeline")
            logger.info("=" * 80)

            logger.info(f"[1/7] Configuration loaded: {self.settings.gmail.account_email}")
            self._authenticate_gmail()
            self._authenticate_sheets()

            message_ids = self._search_messages()
            if not message_ids:
                logger.warning("No emails found matching criteria")
                return {
                    "written": 0,
                    "skipped": 0,
                    "recovered": 0,
                    "transferred": 0,
                    "already_exists": 0,
                }

            message_id = self._select_latest_message(message_ids)

            mt940_file = self._download_and_parse(message_id)
            if not mt940_file or not mt940_file.transactions:
                logger.warning("No transactions found in attachment")
                return {
                    "written": 0,
                    "skipped": 0,
                    "recovered": 0,
                    "transferred": 0,
                    "already_exists": 0,
                }

            self._validate_mt940_reconciliation(mt940_file)

            dedup = SmartDeduplicationService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                target_sheet="T_EXTRATO",
            )
            logger.info("      Using smart deduplication (checking T_EXTRATO)")

            logger.info("[6.25/7] Attempting to recover existing transaction IDs...")
            recovery = TransactionRecoveryService(
                sheets_client=self.sheets_client,
                spreadsheet_id=self.settings.sheets.spreadsheet_id,
                source_sheet="T_EXTRATO",
            )
            recovered_ids = recovery.recover_batch(mt940_file)
            if recovered_ids:
                logger.info(f"      Recovered {len(recovered_ids)} existing IDs from T_EXTRATO")

            result = self._write_to_sheets(mt940_file, dedup)
            written_ids = result.get("written_ids", [])

            all_ids = recovered_ids + written_ids
            logger.info(
                f"      Total IDs for transfer: {len(all_ids)} "
                f"(recovered: {len(recovered_ids)}, new: {len(written_ids)})"
            )

            logger.info("[7/7] Transferring to CONTAORDEM with matching...")
            if self.settings.enable_matching:
                transfer_result = self._transfer_with_matching(all_ids)
            else:
                transfer_result = self._transfer_to_contaordem(all_ids)

            if not self.sheets_client:
                raise RuntimeError("Sheets client not initialized")
            sort_result = self.sheets_client.ensure_contaordem_sorted(
                self.settings.sheets.spreadsheet_id
            )
            if sort_result.get("sorted"):
                logger.info(
                    "      CONTAORDEM sorted by DATA MOV. descending"
                )

            cash_balance_result = None
            if self.settings.cash_balance.update_enabled:
                cash_balance_result = self._update_cash_balance(
                    mt940_file.footer.saldo_fecho,
                    mt940_file.header.saldo_abertura,
                )

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
                        logger.info(
                            f"  - Cash balance updated in {cash_balance_result['target_cell']}"
                        )
            logger.info("=" * 80)
            return {
                "written": result["written"],
                "skipped": result["skipped"],
                "recovered": len(recovered_ids),
                "transferred": transfer_result["transferred"],
                "already_exists": transfer_result["already_exists"],
            }
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise

    def _authenticate_gmail(self) -> None:
        """Authenticate with Gmail API."""
        try:
            if self.gmail_client is not None:
                return
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
            if self.sheets_client is not None:
                if not self.sheets_writer:
                    self.sheets_writer = SheetsWriter(
                        sheets_client=self.sheets_client,
                        spreadsheet_id=self.settings.sheets.spreadsheet_id,
                        sheet_name=self.settings.sheets.sheet_name,
                    )
                return
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

    def _download_and_parse(self, message_id: str):
        """Download and parse MT940 attachment."""
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")
        logger.info("[5/7] Downloading and parsing MT940...")
        return download_and_parse_attachment(self.gmail_client, message_id)

    def _select_latest_message(self, message_ids: list[str]) -> str:
        """Compatibility wrapper for latest-message selection."""
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")
        return select_latest_message(self.gmail_client, message_ids)

    def _validate_mt940_reconciliation(self, mt940_file) -> dict:
        """Compatibility wrapper for MT940 reconciliation validation."""
        return validate_mt940_reconciliation(mt940_file)

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
        """Transfer to CONTAORDEM with integrated matching."""
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
        """Update cash balance in GERENCIAR CAIXAS with safety checks."""
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

            decision = cash_service.should_update_balance(
                closing_balance=Decimal(str(closing_balance)),
                opening_balance=Decimal(str(opening_balance)),
            )

            if not decision.should_update:
                logger.info(f"      Balance update skipped: {decision.reason}")
                if decision.is_historical:
                    logger.info(
                        "      (This is a historical/backfill file - balance will not regress)"
                    )
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
        """Archive the email after successful processing."""
        if not self.gmail_client:
            raise RuntimeError("Gmail client not initialized")
        logger.info("[9/9] Moving email to backup folder...")
        logger.info(f"      Using backup label '{self.settings.gmail.backup_label_name}'")
        archive_email(self.gmail_client, message_id, self.settings.gmail.backup_label_name)
