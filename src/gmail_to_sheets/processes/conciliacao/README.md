# Conciliacao Process

This process reconciles source sheets against `CONTAORDEM` and fills `DOC.SOMA` when a valid match is found.

## Flow

1. Authenticate with Google Sheets
2. Load candidate rows from the source sheet
3. Check that `DOC.SOMA` is empty and `ID_INTERNO` is present
4. Look up matching records in `CONTAORDEM` by `ID_INTERNO`
5. Accept the match only when the target `DOC.SOMA` is exactly 7 numeric
   characters (e.g. `5470146`); other values (empty, `ANALISAR`, wrong
   length) are treated as "not found" and retried later
6. Update the source sheet in batch

## Main Services

- `validator.py`
- `lookup_service.py`
- `reconciliation_service.py`
- `orchestrator.py`

## Notes

- The process uses `ID_INTERNO` as the lookup key.
- The target `DOC.SOMA` format is enforced by `is_valid_doc_soma()` in
  `lookup_service.py` (7 numeric characters).
- Failed matches are skipped and can be retried in a later run.

