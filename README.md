# gmail-to-sheets

Python pipeline to extract MT940 attachments from Gmail and write processed data to Google Sheets.

## Overview

The application:

1. Connects to a Gmail account via OAuth
2. Searches for emails with the expected sender and attachment type
3. Downloads and parses MT940 attachments
4. Validates and normalizes the data
5. Writes results to Google Sheets
6. Prevents duplicates and reprocessing
7. Logs each step for audit and debugging

## Main Features

- Modular architecture
- OAuth 2.0 authentication
- Environment-based configuration
- Structured logging
- Idempotent writes
- Deduplication
- Batch processing
- Automated tests

## Local Usage

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
python -m src.gmail_to_sheets
```

## Configuration

Set the required values in `.env` and place the credential files under `credentials/`.

## Current Production

Production currently runs on the remote server at:

- Host: `opc@servidor-tesouraria`
- Directory: `/home/opc/AppExtrato`
- Runtime: `systemd`

See:

- [`SERVER_PATH.md`](SERVER_PATH.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)

## Project Structure

```text
src/gmail_to_sheets/   Application package
tests/                 Test suite
credentials/           OAuth and service account files
data/                  Downloaded attachments
logs/                  Application logs
```

