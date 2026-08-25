# DIZIMOS/OFERTAS Structure

This document summarizes the source sheet used by the Entradas process.

## Purpose

`DIZIMOS/OFERTAS` is the input sheet for manual entries that can be transferred to `CONTAORDEM`.

## Key Fields

- `DATA`
- `TIPO`
- `DOC. SOMA`
- `NUMERO DOCUMENTO`
- `VALOR`
- `FINANCE`
- `ID_INTERNO`

## Transfer Rules

- `TIPO` must match the expected entry types.
- `DOC. SOMA` must be empty before transfer.
- `FINANCE` must be empty before transfer.
- `VALOR` must be greater than zero.
- `DATA` must be present and valid.

## Transfer Mapping

- `DATA` -> `DATA MOV.`
- `NUMERO DOCUMENTO` -> part of `DESCRICAO`
- `VALOR` -> `IMPORTANCIA`
- `ID_INTERNO` -> copied as-is
- `TIPO` -> fixed target type `Entrada`

## Notes

- `ID_INTERNO` already exists in the source sheet.
- `DOC. SOMA` is filled after transfer to mark the row as processed.
- `FINANCE = Transferido` is used to prevent reprocessing.
