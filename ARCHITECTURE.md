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
- Process health and operational state

## Central Orchestrator

Production uses a single scheduler entrypoint:

- `CentralOrchestrator`
- `ProcessRegistry`
- managed processes with a shared interface:
  - `check_pending()` is read-only
  - `run()` performs the real work

The scheduler wakes every 60 seconds, checks each registered process in priority order, and only runs processes that report pending work.

Execution is sequential. Two managed processes are never started in parallel by the central scheduler.

## Read-only pending probes

Pending probes are designed to be cheap and non-destructive.

- `Extrato`: Gmail search with `max_results=1`
- `Entradas`: reads only the projected column window required by `EntryValidator` and stops logical scanning after the first valid row
- `Conciliacao`: reads only `DOC. SOMA` and `ID_INTERNO` from the source, then projects only `ID_INTERNO` and `DOC. SOMA` from `CONTAORDEM`

Sheet headers are cached in the shared process context for the lifetime of the service. A service restart refreshes this metadata cache.

The projection helper preserves original column indexes by left-padding projected rows before existing validators consume them.

## Process health

The orchestrator persists a lightweight local health snapshot in:

`data/orchestrator-health.json`

The file contains operational metadata only. It does not contain Google credentials, tokens, private keys, spreadsheet cell data, or email contents.

Per-process health includes:

- current state: `IDLE`, `SUCCESS`, or `FAILED`
- last check time
- last run time
- last successful run
- last failure
- consecutive failure count
- last duration
- last error summary
- last pending count

The `status` CLI reads this local file only and does not call Gmail or Google Sheets APIs.

After three consecutive failures for one process, the orchestrator writes a `PROCESS HEALTH ALERT` at CRITICAL level to the normal application/systemd logs. Additional reminders are emitted every ten consecutive failures.

A successful run or a clean idle check resets the consecutive failure counter.

## Main Processes

- `Extrato`: imports MT940 attachments and writes them to Google Sheets
- `Entradas`: transfers validated manual entries from `DIZIMOS/OFERTAS` to `CONTAORDEM`
- `Conciliacao`: fills `DOC.SOMA` by matching rows against `CONTAORDEM`

## How to add a new managed process

1. Implement the managed-process interface with `name`, `priority`, `check_pending()`, and `run()`.
2. Keep `check_pending()` read-only and cheap.
3. Project only fields needed to determine whether work exists.
4. Reuse existing validators and services instead of duplicating business rules.
5. Register the new process in `ProcessRegistry`.
6. Add unit tests for pending detection, execution, health state, and scheduler ordering.

## Runtime

- Production runs on the remote server through `systemd`
- Docker is available for local or future container-based work
- Runtime health is written under `data/`, which is ignored by Git

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`SERVER_PATH.md`](SERVER_PATH.md)
