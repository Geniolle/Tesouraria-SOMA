# CLI Reference

Commands for the application CLI.

## Run Modes

```bash
python -m src.gmail_to_sheets.app run-scheduled
python -m src.gmail_to_sheets.app run-once
python -m src.gmail_to_sheets.app conciliacao
python -m src.gmail_to_sheets.app conciliacao T_EXTRATO
python -m src.gmail_to_sheets.app status
```

## Notes

- `run-scheduled` is the scheduled mode used by the production service.
- `run-once` is useful for local validation and debugging.
- `conciliacao` runs the reconciliation process for the selected sheet.

## Quick Validation

```bash
python -m src.gmail_to_sheets.app run-once
timeout 5m python -m src.gmail_to_sheets.app run-scheduled
```

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)

