# DÍZIMOS/OFERTAS Structure

This document summarizes the source sheet used by the
`DizimosOfertas` managed process.

## Purpose

`DÍZIMOS/OFERTAS` is the input sheet for manual entries that can be
transferred to `CONTAORDEM`.

## Key Fields

- `DATA`
- `TIPO`
- `DOC. SOMA`
- `NÚMERO DOCUMENTO`
- `VALOR`
- `FINANCE`
- `ID_INTERNO`

## Transfer Rules

A row is finance-ready when:

- `DATA` is filled
- `TIPO` is `DÍZIMOS/OFERTAS` or `DIA VERBO MISSÔES`
- `DOC. SOMA` is filled
- `FINANCE` is empty
- `VALOR > 0`

The managed pending probe also excludes rows already present in
`CONTAORDEM` by `ID_INTERNO` or by the normalized
`DATA + VALOR + DESCRIÇÃO` business key.

## Transfer Mapping

- `DATA` -> `DATA MOV.`
- `NÚMERO DOCUMENTO` -> part of `DESCRIÇÃO`
- `VALOR` -> `IMPORTÂNCIA`
- `ID_INTERNO` -> copied as-is
- target `TIPO` -> `Entrada`
- target `PROCESSO` -> `DÍZIMOS/OFERTAS`

## Completion

After successful transfer:

`FINANCE = Transferido`

This prevents reprocessing by the source transfer pipeline.
