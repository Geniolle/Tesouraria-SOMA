# Conciliacao Process

This process reconciles source sheets against `CONTAORDEM` and fills `DOC.SOMA` when a valid match is found.

## Flow

1. Authenticate with Google Sheets
2. Load candidate rows from the source sheet
3. Check that `DOC.SOMA` is empty and `ID_INTERNO` is present
4. Look up matching records in `CONTAORDEM`
5. Validate the matched `DOC.SOMA`
6. Update the source sheet in batch

## Main Services

- `validator.py`
- `lookup_service.py`
- `reconciliation_service.py`
- `orchestrator.py`

## Notes

- The process uses `ID_INTERNO` as the lookup key.
- Failed matches are skipped and can be retried in a later run.

