# SAÍDAS Process

Transfers finance-ready rows from `SAÍDAS` to `CONTAORDEM`.

## Pending criteria

A row is eligible only when:

- `ID_INTERNO` follows `SAI##########`
- `DATA` is filled
- `TIPO = PAGAMENTO`
- `STATUS DA TESOURARIA = Concluído`
- `DOC. SOMA` is empty (never filled)
- `FINANCE` is empty **or** the soft flag `duplicado` (see below)
- `VALOR DA COMPRA > 0`

## Transfer

The process maps the source fields to `CONTAORDEM`, keeps the amount
positive with target `TIPO = Saída`, sets `PROCESSO = SAÍDAS`, and
preserves `ID_INTERNO`.

`FORMA DE PAGAMENTO` is normalized on the way in:

- source contains `DINHEIRO` -> `DINHEIRO`
- source empty -> empty
- anything else -> `TRANSFERÊNCIA BANCÁRIA`

`DESCRIÇÃO SOMA` gets the global `N###` sequence suffix
(`ContaOrdemSequenceService`), scoped per `DATA MOV.` day and
`PROCESSO = SAÍDAS`. Any existing suffix on the source value is replaced,
not duplicated.

Duplicate protection uses both:

- `ID_INTERNO`
- business key `DATA + VALOR + DESCRIÇÃO`

When a row is already in `CONTAORDEM`, it is **not** appended again and the
source `FINANCE` field is set to `duplicado`. After a successful append,
`FINANCE` is set to `Enviado`.

`duplicado` is a **soft** flag, not a terminal state: every run re-checks
those rows against `CONTAORDEM`. If the matching `CONTAORDEM` row is gone
(e.g. removed by hand), the flag no longer matches, the row is transferred
normally and `FINANCE` becomes `Enviado`. A row still matching just keeps
its `duplicado` flag with no extra write. `Enviado` and any other value
remain terminal and block the row.

The central orchestrator performs a read-only pending probe first. A tick
with only still-valid `duplicado` rows (nothing to write) is skipped; the
CONTAORDEM re-check in the probe runs only when no cheaper row is pending.
