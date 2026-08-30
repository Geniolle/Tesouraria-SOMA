# Architecture Overview

This project is a modular Python pipeline for Gmail MT940 processing and sheet synchronization.

## Main Layers

- Configuration and settings
- Gmail client and Sheets client
- MT940 parsing
- Validation and deduplication
- Sheet writing and transfer logic
- Process orchestrators
- Central orchestration layer

## Central Orchestrator

Production now uses a single scheduler entrypoint:

- `CentralOrchestrator`
- `ProcessRegistry`
- managed processes with a shared interface:
  - `check_pending()` is read-only
  - `run()` performs the real work

The scheduler wakes every 60 seconds, checks each registered process in priority order, and only runs processes that report pending work.

## Main Processes

- `Extrato`: imports MT940 attachments and writes them to Google Sheets
- `Entradas`: transfers validated manual entries from `DIZIMOS/OFERTAS` to `CONTAORDEM`
- `Conciliacao`: fills `DOC.SOMA` by matching rows against `CONTAORDEM`

## How to add a new managed process

1. Implement the managed-process interface with `name`, `priority`, `check_pending()`, and `run()`.
2. Keep `check_pending()` read-only and cheap.
3. Reuse existing validators and services instead of duplicating business rules.
4. Register the new process in `ProcessRegistry`.
5. Add unit tests for pending detection, execution, and scheduler ordering.

## Runtime

- Production runs on the remote server through `systemd`
- Docker is available for local or future container-based work

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`SERVER_PATH.md`](SERVER_PATH.md)

