# Extrato Process

This process handles MT940 bank statements downloaded from Gmail and writes the results to Google Sheets.

## Flow

1. Load configuration
2. Authenticate with Gmail
3. Authenticate with Google Sheets
4. Search for messages with attachments
5. Download and parse MT940 files
6. Validate reconciliation totals
7. Deduplicate and write to `T_EXTRATO`
8. Transfer records to `CONTAORDEM`
9. Apply matching when enabled
10. Update cash balance when enabled
11. Archive the processed email when enabled

## Main Services

- `attachment_processor.py`
- `smart_deduplication_service.py`
- `transaction_recovery_service.py`
- `sheets_writer.py`
- `transfer_service.py`
- `transfer_matching_service.py`
- `cash_balance_service.py`
- `matching_service.py`

## Notes

- This process is designed to be idempotent.
- Shared helpers remain in the common `services/` package when reused by more than one process.

