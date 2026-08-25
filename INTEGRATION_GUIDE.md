# Integration Guide

This project integrates Gmail, Google Sheets, MT940 parsing, validation, and process orchestration.

## Integration Points

- Gmail OAuth and message retrieval
- Attachment download and MT940 parsing
- Google Sheets read/write operations
- Deduplication and transfer logic
- Scheduled execution through the application CLI

## Process Integration

- `Extrato` reads Gmail attachments and writes to Google Sheets
- `Entradas` moves validated manual entries to `CONTAORDEM`
- `Conciliacao` fills `DOC.SOMA` using matches from `CONTAORDEM`

## Operational Notes

- Production uses the remote `systemd` service
- Local validation uses `run-once` and the unit test suite
- Docker remains a support option, not the active production runtime

## Related Docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`PROCESSES.md`](PROCESSES.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)

