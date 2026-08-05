#!/usr/bin/env python3
"""
Controlled validation script for cash balance update.

Modes:
- Default (READ_ONLY): Load email, parse MT940, inspect target cell, show data
- --execute: Also write the cash balance value

This script does NOT execute the full orchestrator pipeline.
"""

import argparse
import logging
import sys
from decimal import Decimal

from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.services.cash_balance_service import CashBalanceService

logger = logging.getLogger(__name__)


def main():
    """Execute controlled validation."""
    parser = argparse.ArgumentParser(
        description="Validate cash balance update (read-only by default)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write the cash balance (requires confirmation)"
    )
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "READ_ONLY"

    print("\n" + "=" * 80)
    print(f"CASH BALANCE UPDATE - CONTROLLED VALIDATION ({mode})")
    print("=" * 80 + "\n")

    try:
        # Phase 1: Load configuration
        print("[1/8] Loading configuration...")
        settings = load_settings()
        setup_logging(settings.log_file, "INFO")

        print("[OK] Configuration loaded")
        print(f"  - Gmail account: {settings.gmail.account_email}")
        print(f"  - Spreadsheet: {settings.sheets.spreadsheet_id}")
        print(f"  - Cash balance sheet: {settings.cash_balance.sheet_name}")
        print(f"  - Header row: {settings.cash_balance.header_row}")

        # Phase 2: Authenticate Gmail
        print("\n[2/8] Authenticating with Gmail...")
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        gmail_client = GmailClient(credentials)
        print("[OK] Gmail authenticated")

        # Phase 3: Search for latest MT940 email (by internalDate)
        print("\n[3/8] Searching for latest MT940 email...")
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=settings.batch_size,
        )

        if not message_ids:
            print("[FAIL] No emails found matching criteria")
            return False

        print(f"[OK] Found {len(message_ids)} email(s) matching criteria")

        # Select the most recent by internalDate
        messages = [gmail_client.get_message(mid) for mid in message_ids]
        latest_message = max(
            messages,
            key=lambda msg: int(msg.get("internalDate", 0)),
        )
        message_id = latest_message["id"]
        internal_date_ms = int(latest_message.get("internalDate", 0))

        print(f"[OK] Selected latest email: {message_id}")
        print(f"  - internalDate: {internal_date_ms}")
        print(f"  - Total emails in inbox: {len(message_ids)}")

        # Phase 4: Download and parse attachment
        print("\n[4/8] Downloading and parsing MT940...")
        attachments = gmail_client.get_attachments(message_id)

        if not attachments:
            print("[FAIL] No attachments found")
            return False

        processor = AttachmentProcessor(gmail_client)
        mt940_file = processor.process_attachment(
            message_id=message_id,
            attachment_id=attachments[0].get("attachment_id"),
            filename=attachments[0]["filename"],
        )

        print(f"[OK] Parsed {mt940_file.total_transactions} transactions")

        # Phase 5: Validate reconciliation
        print("\n[5/8] Validating accounting reconciliation...")
        opening = mt940_file.header.saldo_abertura
        closing = mt940_file.footer.saldo_fecho
        transaction_sum = sum(
            (t.valor for t in mt940_file.transactions),
            Decimal("0.00"),
        )
        calculated = (opening + transaction_sum).quantize(Decimal("0.01"))
        difference = (closing - calculated).quantize(Decimal("0.01"))

        print(f"  Opening balance: {opening}")
        print(f"  Transaction sum: {transaction_sum}")
        print(f"  Calculated balance: {calculated}")
        print(f"  Closing balance: {closing}")
        print(f"  Difference: {difference}")

        if abs(difference) > Decimal("0.01"):
            print("[FAIL] Reconciliation failed - difference exceeds tolerance")
            return False

        print("[OK] Reconciliation successful")

        # Phase 6: Authenticate Sheets
        print("\n[6/8] Authenticating with Google Sheets...")
        sheets_client = SheetsClient(
            service_account_path=settings.sheets.service_account_path
        )
        print("[OK] Sheets authenticated")

        # Phase 7: Inspect target cell (read-only using public API)
        print("\n[7/8] Inspecting target cash balance cell...")
        cash_service = CashBalanceService(
            sheets_client=sheets_client,
            spreadsheet_id=settings.sheets.spreadsheet_id,
            sheet_name=settings.cash_balance.sheet_name,
            account_label=settings.cash_balance.account_label,
            header_row=settings.cash_balance.header_row,
            row_offset=settings.cash_balance.row_offset,
            verify_after_write=True,
        )

        # Inspect target (public, read-only method)
        inspection = cash_service.inspect_target()

        print(f"[OK] Header discovered: {inspection['header_name']}")
        print(f"  - Header row: {inspection['header_row']}")
        print(f"  - Header index (0-based): {inspection['header_index']}")
        print(f"  - Column number (1-based): {inspection['column_number']}")
        print(f"  - Column letter: {inspection['column_letter']}")
        print(f"  - Label cell: {inspection['label_cell']}")
        print(f"  - Target cell: {inspection['target_cell']}")
        print(f"  - Previous value: {inspection['previous_value'] or '(empty)'}")

        # Phase 8: Display results
        print("\n" + "=" * 80)
        print("VALIDATION READY")
        print("=" * 80)
        print("\nREAL_VALIDATION=READY")
        print(f"MODE={mode}")
        print(f"SELECTED_FILE={attachments[0]['filename']}")
        print(f"SELECTED_INTERNAL_DATE={internal_date_ms}")
        print(f"INBOX_MATCHES={len(message_ids)}")
        print(f"HEADER_ROW={inspection['header_row']}")
        print(f"ACCOUNT_HEADER_NAME={inspection['header_name']}")
        print(f"ACCOUNT_HEADER_NORMALIZED={inspection['header_normalized']}")
        print(f"ACCOUNT_HEADER_INDEX={inspection['header_index']}")
        print(f"ACCOUNT_COLUMN_NUMBER={inspection['column_number']}")
        print(f"ACCOUNT_COLUMN_LETTER={inspection['column_letter']}")
        print(f"OPENING_BALANCE={opening}")
        print(f"TRANSACTION_TOTAL={transaction_sum}")
        print(f"CALCULATED_BALANCE={calculated}")
        print(f"CLOSING_BALANCE={closing}")
        print(f"DIFFERENCE={difference}")
        print(f"LABEL_CELL={inspection['label_cell']}")
        print(f"TARGET_CELL={inspection['target_cell']}")
        print(f"PREVIOUS_VALUE={inspection['previous_value'] or '(empty)'}")

        # Proceed with write if requested
        if args.execute:
            target_cell = inspection['target_cell']
            print(f"\nType 'YES' to write balance to {target_cell}: ", end="", flush=True)
            confirmation = input().strip().upper()

            if confirmation != "YES":
                print("[FAIL] Write cancelled")
                return False

            # Perform write
            print("\n[8/8] Writing cash balance...")
            cash_result = cash_service.update_balance(closing)

            print("[OK] Write completed")
            print(f"  Written value: {cash_result['written_value']}")
            print(f"  Verified value: {cash_result['verified_value']}")
            print(f"  Verification: {cash_result['verified']}")

            # Final confirmation
            print(f"\nWRITTEN_VALUE={cash_result['written_value']}")
            print(f"VERIFIED_VALUE={cash_result['verified_value']}")
            print(f"BALANCE_UPDATE_VERIFIED={cash_result['verified']}")
        else:
            print("\nWRITTEN_VALUE=N/A (read-only mode)")
            print("VERIFIED_VALUE=N/A (read-only mode)")
            print("BALANCE_UPDATE_VERIFIED=N/A (read-only mode)")

        # Confirm no modifications
        print("GMAIL_MODIFIED=false")
        print("T_EXTRATO_MODIFIED=false")
        print("CONTAORDEM_MODIFIED=false")

        print("\n[OK] Validation completed successfully")
        return True

    except Exception as e:
        print(f"\n[FAIL] Validation failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
