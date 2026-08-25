# Architecture Overview

This project is a modular Python pipeline for Gmail MT940 processing and sheet synchronization.

## Main Layers

- Configuration and settings
- Gmail client and Sheets client
- MT940 parsing
- Validation and deduplication
- Sheet writing and transfer logic
- Process orchestrators

## Main Processes

- `Extrato`: imports MT940 attachments and writes them to Google Sheets
- `Entradas`: transfers validated manual entries from `DIZIMOS/OFERTAS` to `CONTAORDEM`
- `Conciliacao`: fills `DOC.SOMA` by matching rows against `CONTAORDEM`

## Runtime

- Production runs on the remote server through `systemd`
- Docker is available for local or future container-based work

## Related Docs

- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`SERVER_PATH.md`](SERVER_PATH.md)

