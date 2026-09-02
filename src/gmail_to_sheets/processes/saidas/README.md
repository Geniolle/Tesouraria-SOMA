# SAÍDAS Process

Transfers finance-ready rows from `SAÍDAS` to `CONTAORDEM`.

## Pending criteria

A row is eligible only when:

- `ID_INTERNO` follows `SAI##########`
- `DATA` is filled
- `TIPO = PAGAMENTO`
- `STATUS DA TESOURARIA = Concluído`
- `DOC. SOMA` is empty (never filled)
- `FINANCE` is empty
- `VALOR DA COMPRA > 0`

## Transfer

The process maps the source fields to `CONTAORDEM`, keeps the amount
positive with target `TIPO = Saída`, sets `PROCESSO = SAÍDAS`, and
preserves `ID_INTERNO`.

Duplicate protection uses both:

- `ID_INTERNO`
- business key `DATA + VALOR + DESCRIÇÃO`

After a successful append, the source `FINANCE` field is set to
`Enviado`.

The central orchestrator performs a read-only pending probe first. If
there is no eligible non-duplicate row, the process is skipped.
