# Entradas Process

This process handles manual entries from the DIZIMOS/OFERTAS sheet and transfers valid rows to `CONTAORDEM`.

## Flow

1. Authenticate with Google Sheets
2. Load rows from `DIZIMOS/OFERTAS`
3. Validate business rules
4. Deduplicate against `CONTAORDEM`
5. Transfer valid rows
6. Mark processed rows with `FINANCE = Transferido`
7. Sort the target sheet

## Main Services

- `entry_validator.py`
- `entry_deduplication.py`
- `entry_transfer_service.py`
- `entry_status_updater.py`

## Notes

- The process is idempotent.
- Hardcoded business values are intentional here and differ from the Extrato process.

