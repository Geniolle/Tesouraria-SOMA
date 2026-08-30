# CLI Reference

Commands for the application CLI.

## Run Modes

```bash
python -m src.gmail_to_sheets.app run-scheduled
python -m src.gmail_to_sheets.app run-once
python -m src.gmail_to_sheets.app extrato
python -m src.gmail_to_sheets.app dizimos-ofertas
python -m src.gmail_to_sheets.app entradas
python -m src.gmail_to_sheets.app saidas
python -m src.gmail_to_sheets.app conciliacao
python -m src.gmail_to_sheets.app check-inbox
python -m src.gmail_to_sheets.app status
```

## Notes

- `run-scheduled` is the 60-second central scheduler used by systemd.
- `run-once` executes one intelligent orchestration tick.
- `extrato` runs only the Gmail MT940 extraction.
- `dizimos-ofertas` runs the `DÍZIMOS/OFERTAS -> CONTAORDEM` transfer.
- `entradas` is a backward-compatible alias for `dizimos-ofertas`.
- `saidas` runs the `SAÍDAS -> CONTAORDEM` transfer.
- `conciliacao` runs reconciliation for the selected source sheet.
- `check-inbox` is read-only.
- `status` reads local process health and does not call external APIs.

## Health Status

Typical output:

```text
AppExtrato Orchestrator
Scheduler interval: 60 seconds
Processes:
  Extrato         priority=10 state=IDLE
  DizimosOfertas  priority=20 state=IDLE
  Saidas          priority=30 state=IDLE
  Conciliacao     priority=40 state=SUCCESS
```

States:

- `IDLE`: pending check succeeded and there is no actionable work.
- `SUCCESS`: the last real execution completed successfully.
- `FAILED`: the pending check or process execution failed.

After three consecutive failures for the same process, a
`PROCESS HEALTH ALERT` is written at CRITICAL level to the
application/systemd logs.

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
