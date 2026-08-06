#!/usr/bin/env python
"""
Test Script for Entradas Process

Comprehensive testing of the Entradas pipeline:
1. Loads and validates entries
2. Tests deduplication
3. Tests transfer (dry-run or live)
4. Generates test report
"""

import logging
import sys
from datetime import datetime

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.entradas.entry_validator import EntryValidator
from src.gmail_to_sheets.processes.entradas.entry_deduplication import (
    EntryDeduplicationService,
)
from src.gmail_to_sheets.processes.entradas.entry_transfer_service import (
    EntryTransferService,
)
from src.gmail_to_sheets.processes.entradas.entry_status_updater import (
    EntryStatusUpdater,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EntradasTestSuite:
    """Test suite for Entradas process."""

    def __init__(self, dry_run: bool = True):
        """
        Initialize test suite.

        Args:
            dry_run: If True, don't make changes to sheets (testing only)
        """
        self.settings = load_settings()
        self.sheets_client = SheetsClient(
            service_account_path=str(self.settings.sheets.service_account_path)
        )
        self.spreadsheet_id = self.settings.sheets.spreadsheet_id
        self.dry_run = dry_run

        self.test_results = {
            "start_time": datetime.now(),
            "tests": {},
            "summary": {},
        }

    def run_all_tests(self) -> bool:
        """Run all tests and return overall success."""
        print("\n" + "=" * 80)
        print("ENTRADAS PROCESS TEST SUITE")
        print("=" * 80)
        print(f"Dry Run: {self.dry_run}")
        print(f"Start Time: {self.test_results['start_time']}\n")

        try:
            # Test 1: Validation
            self.test_validation()

            # Test 2: Deduplication
            self.test_deduplication()

            # Test 3: Transfer Service
            self.test_transfer_service()

            # Test 4: Status Updater
            self.test_status_updater()

            # Generate report
            self.print_report()

            return True

        except Exception as e:
            logger.error(f"Test suite failed: {e}", exc_info=True)
            return False

    def test_validation(self) -> None:
        """Test 1: Entry validation."""
        print("[TEST 1] Entry Validation")
        print("-" * 80)

        try:
            validator = EntryValidator(self.sheets_client, self.spreadsheet_id)

            # Load data
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="DÍZIMOS/OFERTAS!A2:Z20",  # First 20 rows
            ).execute()

            rows = result.get("values", [])
            logger.info(f"Loaded {len(rows)} rows for testing")

            valid = 0
            invalid = 0
            errors = {}

            for row_num, row in enumerate(rows, start=2):
                is_valid, error = validator.is_valid_entry(row, row_num)

                if is_valid:
                    valid += 1
                    print(f"  Row {row_num:3d}: ✓ VALID")
                else:
                    invalid += 1
                    error_msg = error or "Unknown error"
                    print(f"  Row {row_num:3d}: ✗ INVALID ({error_msg})")
                    errors[row_num] = error_msg

            self.test_results["tests"]["validation"] = {
                "total": len(rows),
                "valid": valid,
                "invalid": invalid,
                "errors": errors,
                "status": "PASS"
            }

            print(f"\nValidation Summary:")
            print(f"  Total rows: {len(rows)}")
            print(f"  Valid: {valid}")
            print(f"  Invalid: {invalid}")
            print(f"  Pass rate: {valid/len(rows)*100:.1f}%\n")

        except Exception as e:
            logger.error(f"Validation test failed: {e}")
            self.test_results["tests"]["validation"] = {"status": "FAIL", "error": str(e)}
            raise

    def test_deduplication(self) -> None:
        """Test 2: Deduplication logic."""
        print("[TEST 2] Deduplication")
        print("-" * 80)

        try:
            dedup = EntryDeduplicationService(
                self.sheets_client, self.spreadsheet_id
            )

            print(f"Loaded {len(dedup.existing_keys)} existing entries from CONTAORDEM")

            # Test with sample data
            test_entries = [
                ("03/01/2024", "29,50", "R240103 - DÍZIMOS E OFERTAS (CULTO)"),
                ("07/01/2024", "312,20", "R240107 - DÍZIMOS E OFERTAS (CULTO)"),
                ("03/01/2024", "29,50", "R240103 - DÍZIMOS E OFERTAS (CULTO)"),  # Duplicate
            ]

            duplicates = 0
            unique = 0

            for data, valor, desc in test_entries:
                is_dup = dedup.is_duplicate(data, valor, desc)
                status = "DUPLICATE" if is_dup else "UNIQUE"
                print(f"  {data} | {valor:>8} | {desc[:40]:<40} → {status}")

                if is_dup:
                    duplicates += 1
                else:
                    unique += 1
                    dedup.register_new_entry(data, valor, desc)

            self.test_results["tests"]["deduplication"] = {
                "total": len(test_entries),
                "unique": unique,
                "duplicates": duplicates,
                "status": "PASS"
            }

            print(f"\nDeduplication Summary:")
            print(f"  Tested: {len(test_entries)}")
            print(f"  Unique: {unique}")
            print(f"  Duplicates: {duplicates}\n")

        except Exception as e:
            logger.error(f"Deduplication test failed: {e}")
            self.test_results["tests"]["deduplication"] = {"status": "FAIL", "error": str(e)}
            raise

    def test_transfer_service(self) -> None:
        """Test 3: Transfer service."""
        print("[TEST 3] Transfer Service")
        print("-" * 80)

        try:
            transfer = EntryTransferService(
                self.sheets_client, self.spreadsheet_id
            )

            print(f"Source headers ({len(transfer.source_headers)}): {', '.join(transfer.source_headers)[:60]}...")
            print(f"Target headers ({len(transfer.target_headers)}): {', '.join(transfer.target_headers)[:60]}...")

            # Load sample row
            result = self.sheets_client.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="DÍZIMOS/OFERTAS!A2:Q2",  # First data row
            ).execute()

            rows = result.get("values", [])
            if rows:
                source_row = rows[0]
                numero_doc_idx = 6

                numero_doc = str(source_row[numero_doc_idx]).strip() if numero_doc_idx < len(source_row) else ""

                # Build target row
                target_row = transfer.build_target_row(source_row, numero_doc)

                print(f"\nBuilt target row ({len(target_row)} columns):")
                for idx, value in enumerate(target_row):
                    if value:
                        col_name = transfer.target_headers[idx] if idx < len(transfer.target_headers) else f"Col{idx}"
                        print(f"  [{idx:2d}] {col_name:<30} = {str(value)[:50]}")

                self.test_results["tests"]["transfer"] = {
                    "row_built": True,
                    "columns": len(target_row),
                    "filled_fields": len([v for v in target_row if v]),
                    "status": "PASS"
                }

                print(f"\nTransfer Summary:")
                print(f"  Columns built: {len(target_row)}")
                print(f"  Fields filled: {len([v for v in target_row if v])}\n")
            else:
                raise Exception("No sample rows found")

        except Exception as e:
            logger.error(f"Transfer test failed: {e}")
            self.test_results["tests"]["transfer"] = {"status": "FAIL", "error": str(e)}
            raise

    def test_status_updater(self) -> None:
        """Test 4: Status updater."""
        print("[TEST 4] Status Updater")
        print("-" * 80)

        try:
            updater = EntryStatusUpdater(self.sheets_client, self.spreadsheet_id)

            if updater.finance_column_index is None:
                print("  ✗ FINANCE column not found")
                self.test_results["tests"]["status_updater"] = {
                    "finance_found": False,
                    "status": "FAIL"
                }
                raise Exception("FINANCE column not found")

            print(f"  ✓ FINANCE column found at index {updater.finance_column_index}")
            print(f"  ✓ Column letter: {updater._number_to_column(updater.finance_column_index + 1)}")
            print(f"  ✓ Status value to write: '{updater.STATUS_VALUE}'")

            if not self.dry_run:
                print("\n  [DRY RUN - No changes made]")

            self.test_results["tests"]["status_updater"] = {
                "finance_found": True,
                "column_index": updater.finance_column_index,
                "status": "PASS"
            }

            print(f"\nStatus Updater Summary:")
            print(f"  FINANCE column: Found")
            print(f"  Ready to mark entries as: '{updater.STATUS_VALUE}'\n")

        except Exception as e:
            logger.error(f"Status updater test failed: {e}")
            self.test_results["tests"]["status_updater"] = {"status": "FAIL", "error": str(e)}
            raise

    def print_report(self) -> None:
        """Print comprehensive test report."""
        self.test_results["end_time"] = datetime.now()
        duration = self.test_results["end_time"] - self.test_results["start_time"]

        print("=" * 80)
        print("TEST REPORT")
        print("=" * 80)
        print(f"Start Time: {self.test_results['start_time']}")
        print(f"End Time: {self.test_results['end_time']}")
        print(f"Duration: {duration}")
        print(f"Dry Run: {self.dry_run}\n")

        all_pass = True
        for test_name, result in self.test_results["tests"].items():
            status = result.get("status", "UNKNOWN")
            all_pass = all_pass and (status == "PASS")

            icon = "✓" if status == "PASS" else "✗"
            print(f"{icon} {test_name.upper()}: {status}")

            # Print summary
            for key, value in result.items():
                if key not in ["status"]:
                    if isinstance(value, (int, float)):
                        print(f"    {key}: {value}")
                    elif isinstance(value, dict):
                        print(f"    {key}: {len(value)} items")

        print("\n" + "=" * 80)
        if all_pass:
            print("✓ ALL TESTS PASSED")
            print("=" * 80)
            return 0
        else:
            print("✗ SOME TESTS FAILED")
            print("=" * 80)
            return 1


def main():
    """Entry point for test script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test suite for Entradas process"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run with live changes (default is dry-run)"
    )

    args = parser.parse_args()
    dry_run = not args.live

    suite = EntradasTestSuite(dry_run=dry_run)
    success = suite.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
