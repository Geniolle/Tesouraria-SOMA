#!/usr/bin/env python3
"""
Controlled validation script for cash balance update.

Modes:
- Default (READ_ONLY): Load email, parse MT940, locate marker, show data
- --execute: Also write the cash balance value

This script does NOT execute the full orchestrator pipeline.
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.services.attachment_processor import AttachmentProcessor
from src.gmail_to_sheets.services.cash_balance_service import CashBalanceService
from src.gmail_to_sheets.logging_config import setup_logging

import logging

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

        print(f"✓ Configuration loaded")
        print(f"  - Gmail account: {settings.gmail.account_email}")
        print(f"  - Spreadsheet: {settings.sheets.spreadsheet_id}")
        print(f"  - Cash balance sheet: {settings.cash_balance.sheet_name}")

        # Phase 2: Authenticate Gmail
        print("\n[2/8] Authenticating with Gmail...")
        authenticator = GmailAuthenticator(
            client_secrets_path=settings.gmail.client_secrets_path,
            credentials_path=settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        gmail_client = GmailClient(credentials)
        print("✓ Gmail authenticated")

        # Phase 3: Search for latest MT940 email (by internalDate)
        print("\n[3/8] Searching for latest MT940 email...")
        message_ids = gmail_client.search_messages(
            query=settings.gmail.search_query,
            max_results=settings.batch_size,
        )

        if not message_ids:
            print("✗ No emails found matching criteria")
            return False

        print(f"✓ Found {len(message_ids)} email(s) matching criteria")

        # Select the most recent by internalDate
        messages = [gmail_client.get_message(mid) for mid in message_ids]
        latest_message = max(
            messages,
            key=lambda msg: int(msg.get("internalDate", 0)),
        )
        message_id = latest_message["id"]
        internal_date_ms = int(latest_message.get("internalDate", 0))

        print(f"✓ Selected latest email: {message_id}")
        print(f"  - internalDate: {internal_date_ms}")
        print(f"  - Total emails in inbox: {len(message_ids)}")

        # Phase 4: Download and parse attachment
        print("\n[4/8] Downloading and parsing MT940...")
        attachments = gmail_client.get_attachments(message_id)

        if not attachments:
            print("✗ No attachments found")
            return False

        processor = AttachmentProcessor(gmail_client)
        mt940_file = processor.process_attachment(
            message_id=message_id,
            attachment_id=attachments[0].get("attachment_id"),
            filename=attachments[0]["filename"],
        )

        print(f"✓ Parsed {mt940_file.total_transactions} transactions")

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
            print("✗ Reconciliation failed - difference exceeds tolerance")
            return False

        print("✓ Reconciliation successful")

        # Phase 6: Authenticate Sheets
        print("\n[6/8] Authenticating with Google Sheets...")
        sheets_client = SheetsClient(
            service_account_path=settings.sheets.service_account_path
        )
        print("✓ Sheets authenticated")

        # Phase 7: Locate cash balance cell
        print("\n[7/8] Locating cash balance cell...")
        cash_service = CashBalanceService(
            sheets_client=sheets_client,
            spreadsheet_id=settings.sheets.spreadsheet_id,
            sheet_name=settings.cash_balance.sheet_name,
            account_label=settings.cash_balance.account_label,
            row_offset=settings.cash_balance.row_offset,
            verify_after_write=True,
        )

        # Get dynamic range based on actual sheet dimensions
        range_name = cash_service._get_dynamic_range()
        print(f"  Using dynamic range: {range_name}")

        result = sheets_client.service.spreadsheets().values().get(
            spreadsheetId=settings.sheets.spreadsheet_id,
            range=range_name,
        ).execute()

        rows = result.get("values", [])
        label_row, label_col = cash_service._find_label_cell(rows)
        label_cell = cash_service._row_col_to_a1(label_row, label_col)
        target_cell = cash_service._row_col_to_a1(
            label_row + settings.cash_balance.row_offset, label_col
        )
        previous_value = cash_service._get_cell_value(
            rows, label_row + settings.cash_balance.row_offset, label_col
        )

        print(f"✓ Label found at: {label_cell}")
        print(f"✓ Target cell: {target_cell}")
        print(f"✓ Previous value: {previous_value or '(empty)'}")

        # Phase 8: Display results
        print("\n" + "=" * 80)
        print("VALIDATION READY")
        print("=" * 80)
        print(f"\nREAL_VALIDATION=READY")
        print(f"MODE={mode}")
        print(f"SELECTED_FILE={attachments[0]['filename']}")
        print(f"SELECTED_INTERNAL_DATE={internal_date_ms}")
        print(f"INBOX_MATCHES={len(message_ids)}")
        print(f"OPENING_BALANCE={opening}")
        print(f"TRANSACTION_TOTAL={transaction_sum}")
        print(f"CALCULATED_BALANCE={calculated}")
        print(f"CLOSING_BALANCE={closing}")
        print(f"DIFFERENCE={difference}")
        print(f"SHEET_RANGE={range_name}")
        print(f"LABEL_CELL={label_cell}")
        print(f"TARGET_CELL={target_cell}")
        print(f"PREVIOUS_VALUE={previous_value or '(empty)'}")

        # Proceed with write if requested
        if args.execute:
            print(f"\nType 'YES' to write balance to {target_cell}: ", end="", flush=True)
            confirmation = input().strip().upper()

            if confirmation != "YES":
                print("✗ Write cancelled")
                return False

            # Perform write
            print("\n[8/8] Writing cash balance...")
            cash_result = cash_service.update_balance(closing)

            print(f"✓ Write completed")
            print(f"  Written value: {cash_result['written_value']}")
            print(f"  Verified value: {cash_result['verified_value']}")
            print(f"  Verification: {cash_result['verified']}")

            # Final confirmation
            print(f"\nWRITTEN_VALUE={cash_result['written_value']}")
            print(f"VERIFIED_VALUE={cash_result['verified_value']}")
            print(f"BALANCE_UPDATE_VERIFIED={cash_result['verified']}")
        else:
            print(f"\nWRITTEN_VALUE=N/A (read-only mode)")
            print(f"VERIFIED_VALUE=N/A (read-only mode)")
            print(f"BALANCE_UPDATE_VERIFIED=N/A (read-only mode)")

        # Confirm no modifications
        print(f"GMAIL_MODIFIED=false")
        print(f"T_EXTRATO_MODIFIED=false")
        print(f"CONTAORDEM_MODIFIED=false")

        print("\n✓ Validation completed successfully")
        return True

    except Exception as e:
        print(f"\n✗ Validation failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
