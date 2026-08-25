# Matching Logic

This document summarizes the matching flow used by the Extrato process.

## Goal

Match rows from `CONTAORDEM` against reference data in `CONSTANTES` and fill the derived fields.

## Core Rules

- Use column headers, not hardcoded indexes.
- Validate that required columns exist before processing.
- Load source and reference rows into memory.
- Keep sequence numbers stable per day and per description base.
- Skip rows that already have a final value.

## Main Steps

1. Load headers and build column maps.
2. Validate required columns.
3. Load rows from `CONTAORDEM` and `CONSTANTES`.
4. Build the sequence state for existing rows.
5. Process each eligible row and try to match it.
6. Write the updates back to the sheet.

## Notes

- The Python and JavaScript implementations should follow the same business rules.
- The logic is designed to be deterministic and repeatable.

