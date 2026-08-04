# gmail-to-sheets

A professional Python pipeline to extract MT940 attachments from Gmail emails and write processed data to Google Sheets.

## Overview

This application:
1. Connects to a Gmail account via OAuth
2. Searches for emails matching specific criteria (sender: Montepio, attachment type: `.txt`)
3. Downloads and extracts attachment content
4. Validates and normalizes the data
5. Writes results to a configured Google Sheets document
6. Prevents duplicates and reprocessing
7. Logs all actions for audit and debugging

## Features

- ✓ Modular architecture with clear separation of concerns
- ✓ Type-safe Python with full type hints
- ✓ Secure OAuth 2.0 authentication
- ✓ Configuration via environment variables
- ✓ Structured logging
- ✓ Idempotent operations
- ✓ Deduplication by filename/content hash
- ✓ Batch processing
- ✓ Comprehensive testing

## Setup

### Prerequisites

- Python 3.10+
- Google account with Gmail access
- Google Sheets API enabled
- Google OAuth credentials

### Installation

```bash
# Clone and navigate to project
cd gmail-to-sheets

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### Configuration

1. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

2. Place Google OAuth credentials in `credentials/gmail-client-secret.json`

3. Place Google Sheets service account JSON in `credentials/sheets-service-account.json`

### Usage

```bash
python -m src.gmail_to_sheets
```

## Development

### Running Tests

```bash
pytest
pytest --cov=src/gmail_to_sheets
```

### Linting and Formatting

```bash
ruff check src/
ruff format src/
mypy src/
```

### Logs

Application logs are written to `logs/gmail-to-sheets.log` and stdout (configurable via `LOG_LEVEL`).

## Project Structure

```
src/gmail_to_sheets/     # Main application
  __init__.py
  main.py                # Entry point
  orchestrator.py        # Flow orchestration
  config/                # Configuration management
  clients/               # Gmail and Sheets clients
  services/              # Business logic
  parsers/               # MT940 parsing
  models/                # Data models
  validators/            # Data validation
  exceptions/            # Custom exceptions
  repositories/          # Data access
  logging.py             # Logging setup

tests/                   # Test suite
  unit/
  integration/

credentials/             # OAuth tokens (git-ignored)
data/                    # Downloaded attachments
logs/                    # Application logs
```

## Documentation

- `AGENTS.md` — Permanent development rules
- `.agents/skills/gmail-to-sheets/SKILL.md` — Development skill guide

## License

MIT
