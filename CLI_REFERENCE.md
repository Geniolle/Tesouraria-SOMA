# CLI Reference

Commands for the application CLI.

## Run Modes

```bash
python -m src.gmail_to_sheets.app run-scheduled     # Run central scheduler (tick every 60s)
python -m src.gmail_to_sheets.app run-once          # Run one orchestration tick (checks pending work first)
python -m src.gmail_to_sheets.app extrato           # Run Extrato only (Gmail MT940 download & write)
python -m src.gmail_to_sheets.app entradas          # Run Entradas only (Dízimos/Ofertas transfer)
python -m src.gmail_to_sheets.app check-inbox       # Validate Gmail inbox only (read-only, no modifications)
python -m src.gmail_to_sheets.app conciliacao       # Run Conciliation for T_EXTRATO
python -m src.gmail_to_sheets.app status            # Show local process health without API calls
```

## Notes

- `run-scheduled` is the scheduled mode used by the production service (`systemd`).
- `run-once` executes one central orchestration tick and only runs processes with pending work.
- `extrato` runs only the Gmail MT940 extraction and transfer.
- `entradas` runs only the Dízimos/Ofertas transfer to CONTAORDEM.
- `check-inbox` performs read-only inbox inspection without downloading, modifying, or archiving emails.
- `conciliacao` runs the reconciliation process for the selected sheet.
- `status` reads `data/orchestrator-health.json` and does not contact Gmail or Google Sheets.

## Health Status

Typical output:

```text
AppExtrato Orchestrator
Scheduler interval: 60 seconds
Processes:
  Extrato      priority=10 state=IDLE    failures=0   last_run=... last_success=...
  Entradas     priority=20 state=IDLE    failures=0   last_run=... last_success=...
  Conciliacao  priority=30 state=SUCCESS failures=0   last_run=... last_success=...
```

States:

- `IDLE`: pending check succeeded and there is no work to run.
- `SUCCESS`: the last real execution completed successfully.
- `FAILED`: the pending check or process execution failed.

After three consecutive failures for the same process, a `PROCESS HEALTH ALERT` is written at CRITICAL level to the application/systemd logs.

## Quick Validation

```bash
python -m src.gmail_to_sheets.app status
python -m src.gmail_to_sheets.app run-once
timeout 5m python -m src.gmail_to_sheets.app run-scheduled
```

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
