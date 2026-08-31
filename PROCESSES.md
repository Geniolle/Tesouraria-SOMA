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

### VerboCafe

Imports Verbo Café rows from a **separate** spreadsheet
(`VERBO_CAFE_SOURCE_SPREADSHEET_ID`) into `CONTAORDEM`, in two phases:

- **Vendas** (`VC_VENDAS`): cash sales → `CONTAORDEM` as `Entrada`,
  `PROCESSO = VC_VENDAS`.
- **Pagamentos** (`Financeiro`): supplier payments → `CONTAORDEM` as
  `Saída`, `PROCESSO = FINANCEIRO`.

A source row is ready when `STATUS DA TESOURARIA = EM ABERTO` (and, for
vendas, `FORMA DE PAGAMENTO = DINHEIRO`), `DATA` is valid, the amount
(`VALOR A PAGAR` / `MONTANTE`) is positive and `ID_INTERNO` is filled.

`DESCRIÇÃO SOMA` carries a per-day, per-`PROCESSO` sequence
(`... N001`, `... N002`, …). After a successful append, the source
`STATUS DA TESOURARIA` is set to `CONCLUÍDO`.

### Conciliacao

Matches `T_EXTRATO` rows against `CONTAORDEM` and fills `DOC.SOMA` on
the source sheet when the target already contains an actionable value.

## Central execution order

The registry currently runs sequentially in this order:

1. Extrato — priority 10
2. DizimosOfertas — priority 20
3. Saidas — priority 30
4. VerboCafe — priority 35
5. Conciliacao — priority 40

Every managed process exposes:

- `check_pending()` for read-only work detection
- `run()` for the real execution path
- `priority` for deterministic sequential ordering

Processes without actionable records are skipped.

## Mandatory CONTAORDEM ordering

Whenever any process inserts or updates records in `CONTAORDEM`, the sheet
must finish ordered by:

`DATA MOV.` descending.

This is a global invariant, not a process-specific business rule. The shared
Sheets client tracks mutations and the central orchestrator provides a
fallback enforcement step after every managed process.

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
- [`src/gmail_to_sheets/processes/verbo_cafe/README.md`](src/gmail_to_sheets/processes/verbo_cafe/README.md)
