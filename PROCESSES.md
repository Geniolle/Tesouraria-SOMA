# Processes Overview

This document describes the business processes in the application.

## Processes

### Extrato

Imports MT940 attachments from Gmail and writes normalized transactions to Google Sheets.

### Entradas

Transfers validated manual entries from `DIZIMOS/OFERTAS` to `CONTAORDEM`.

### Conciliacao

Matches rows against `CONTAORDEM` and fills `DOC.SOMA` on the source sheet.

## Structure

Each process has:

- its own folder under `src/gmail_to_sheets/processes/`
- a dedicated `README.md`
- specialized services and an orchestrator

## Related Docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)

