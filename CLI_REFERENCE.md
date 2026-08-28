# CLI Reference

Commands for the application CLI.

## Run Modes

```bash
python -m src.gmail_to_sheets.app run-scheduled     # Run background scheduler (Extrato -> Entradas -> Conciliação every 2m)
python -m src.gmail_to_sheets.app run-once          # Run full pipeline cycle once (Extrato + Entradas + Conciliação)
python -m src.gmail_to_sheets.app extrato           # Run Extrato only (Gmail MT940 download & write)
python -m src.gmail_to_sheets.app entradas          # Run Entradas only (Dízimos/Ofertas transfer)
python -m src.gmail_to_sheets.app check-inbox       # Validate Gmail inbox only (read-only, no modifications)
python -m src.gmail_to_sheets.app conciliacao       # Run Conciliation for T_EXTRATO
python -m src.gmail_to_sheets.app status            # Show scheduler status and registered processes
```

## Notes

- `run-scheduled` is the scheduled mode used by the production service (`systemd`).
- `run-once` executes the complete sequential pipeline (`Extrato` -> `Entradas` -> `Conciliação`).
- `extrato` runs only the Gmail MT940 extraction and transfer.
- `entradas` runs only the Dízimos/Ofertas transfer to CONTAORDEM.
- `check-inbox` performs read-only inbox inspection without downloading, modifying, or archiving emails.
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
