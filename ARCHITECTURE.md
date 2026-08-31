# Architecture Overview

This project is a modular Python pipeline for Gmail MT940 processing and
sheet synchronization.

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

The scheduler wakes every 60 seconds, checks each registered process in
priority order, and only runs processes that report actionable work.

Execution is sequential. Two managed processes are never started in parallel
by the central scheduler.

Current order:

1. `Extrato` — priority 10
2. `DizimosOfertas` — priority 20
3. `Saidas` — priority 30
4. `VerboCafe` — priority 35
5. `Conciliacao` — priority 40

## Read-only pending probes

Pending probes are designed to be cheap and non-destructive.

- `Extrato`: Gmail search with `max_results=1`
- `DizimosOfertas`: projects the fields required by `EntryValidator`,
  checks duplicate protection only after a valid source candidate exists, and
  stops after the first actionable row
- `Saidas`: projects the fields required by `SaidaValidator`, checks
  `CONTAORDEM` only after a finance-ready source candidate exists, and stops
  after the first actionable row
- `VerboCafe`: projects the fields required by `VerboCafeValidator` from the
  external source spreadsheet (`VC_VENDAS`, then `Financeiro`), checks
  `CONTAORDEM` duplicates only after a valid candidate exists, and stops
  after the first actionable row
- `Conciliacao`: reads only `DOC. SOMA` and `ID_INTERNO` from the source,
  then projects only `ID_INTERNO` and `DOC. SOMA` from `CONTAORDEM`

Sheet headers are cached in the shared process context for the lifetime of
the service. A service restart refreshes this metadata cache.

The projection helper preserves original column indexes by left-padding
projected rows before existing validators consume them.

## CONTAORDEM ordering invariant

`CONTAORDEM` has a mandatory post-write invariant:

- base column: `DATA MOV.`
- order: descending (most recent first)
- header row is excluded from sorting

The shared `SheetsClient` tracks sheet mutations. Any managed process that
changes `CONTAORDEM` marks it dirty, and the central orchestrator enforces
the sort before finalizing the process result.

Current process orchestrators also enforce the same invariant on their
standalone/manual execution path.

If the sort fails after a mutation, the managed process is reported as
`FAILED`; the failure is not silently ignored.

This ordering must remain centralized. New processes should not implement
their own independent sort algorithm.

## Process health

The orchestrator persists a lightweight local health snapshot in:

`data/orchestrator-health.json`

The file contains operational metadata only. It does not contain Google
credentials, tokens, private keys, spreadsheet cell data, or email contents.

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

The `status` CLI reads this local file only and does not call Gmail or
Google Sheets APIs.

After three consecutive failures for one process, the orchestrator writes a
`PROCESS HEALTH ALERT` at CRITICAL level to the normal application/systemd
logs. Additional reminders are emitted every ten consecutive failures.

A successful run or a clean idle check resets the consecutive failure
counter.

## How to add a new managed process

1. Implement the managed-process interface with `name`, `priority`,
   `check_pending()`, and `run()`.
2. Keep `check_pending()` read-only and cheap.
3. Project only fields needed to determine whether work exists.
4. Reuse existing validators and services instead of duplicating business
   rules.
5. Register the new process in `ProcessRegistry`.
6. Add unit tests for pending detection, execution, health state, and
   scheduler ordering.

## Runtime

- Production runs on the remote server through `systemd`
- Docker is available for local or future container-based work
- Runtime health is written under `data/`, which is ignored by Git

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`SERVER_PATH.md`](SERVER_PATH.md)
