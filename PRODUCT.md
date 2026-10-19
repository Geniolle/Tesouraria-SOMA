# Tesouraria-SOMA

## Purpose

Tesouraria-SOMA is a Python service that coordinates treasury processes around Gmail attachments, MT940 parsing, reconciliation, and controlled Google Sheets updates.

## Users and operation

The service supports the treasury team and runs locally for development and on the existing production host for scheduled operation. Operational details remain canonical in [PRODUCTION_RUNTIME.md](PRODUCTION_RUNTIME.md), [DEPLOYMENT.md](DEPLOYMENT.md), and [PROCESSES.md](PROCESSES.md).

## Product boundaries

- Preserve idempotent and append/update-only spreadsheet behavior.
- Never expose OAuth tokens, service-account credentials, private keys, or sensitive financial content.
- Keep Gmail processing sequential and observable.
- Keep every `CONTAORDEM` writer compliant with the sorting and `DESCRIÇÃO SOMA` sequence invariants in [AGENTS.md](AGENTS.md).
- Treat production, deployment, migrations, and external writes as separately authorized operations.

## Acceptance criteria

The application remains modular, configurable through environment settings, testable without real external services, and verifiable through the quality gates documented in [docs/quality.md](docs/quality.md).
