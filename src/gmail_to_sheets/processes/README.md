# Processes

This directory contains the business processes used by the application.

## Current Processes

### Extrato

Processes MT940 bank statements downloaded from Gmail.

Main responsibilities:

- download attachments
- parse and validate data
- deduplicate records
- write to Google Sheets
- transfer records to the target sheet
- apply matching when enabled
- update cash balance when enabled

### Entradas

Processes manual entries and related validation logic.

### Conciliacao

Reconciles source records against target records and fills the matching fields.

## Structure Rule

Each process should keep its own documentation and specialized services.

## Shared Services

Common utilities are kept in the shared `services/` package when they are reused by more than one process.

