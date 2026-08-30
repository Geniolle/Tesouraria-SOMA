# Processes Overview

This document describes the business processes in the application.

## Processes

### Extrato

Imports MT940 attachments from Gmail and writes normalized transactions to
Google Sheets.

### DizimosOfertas

Transfers finance-ready manual entries from `DÍZIMOS/OFERTAS` to
`CONTAORDEM`.

The legacy CLI name `entradas` remains available for compatibility, but the
managed process name exposed by the central orchestrator is
`DizimosOfertas`.

### Saidas

Transfers finance-ready rows from `SAÍDAS` to `CONTAORDEM`.

A row is considered ready only when the treasury status is `Concluído`,
`DOC. SOMA` is filled, `FINANCE` is empty, the value is positive, and
the row has a valid `SAI##########` ID.

After a successful transfer, `FINANCE` is marked as `Enviado`.

### Conciliacao

Matches `T_EXTRATO` rows against `CONTAORDEM` and fills `DOC.SOMA` on
the source sheet when the target already contains an actionable value.

## Central execution order

The registry currently runs sequentially in this order:

1. Extrato — priority 10
2. DizimosOfertas — priority 20
3. Saidas — priority 30
4. Conciliacao — priority 40

Every managed process exposes:

- `check_pending()` for read-only work detection
- `run()` for the real execution path
- `priority` for deterministic sequential ordering

Processes without actionable records are skipped.

## Duplicate protection

Finance transfers use both:

- `ID_INTERNO`
- business key `DATA + VALOR + DESCRIÇÃO`

This prevents a row from being appended twice to `CONTAORDEM`.

## Related Docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`src/gmail_to_sheets/processes/saidas/README.md`](src/gmail_to_sheets/processes/saidas/README.md)
