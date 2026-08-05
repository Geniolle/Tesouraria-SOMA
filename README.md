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

#### Environment Variables

**Gmail Configuration:**
- `GMAIL_ACCOUNT_EMAIL` — Gmail account email address
- `GMAIL_SENDER_EMAIL` — Expected sender email for MT940 files
- `GMAIL_SEARCH_QUERY` — Gmail search filter (e.g., `from:noreply@montepio.pt`)
- `GMAIL_LABEL_NAME` — Inbox label for processed emails
- `GMAIL_BACKUP_LABEL_NAME` — Archive label for processed emails
- `GMAIL_CREDENTIALS_PATH` — Path to OAuth token file
- `GMAIL_CLIENT_SECRETS_PATH` — Path to OAuth client secrets file

**Google Sheets Configuration:**
- `SHEETS_SPREADSHEET_ID` — Target spreadsheet ID
- `SHEETS_SHEET_NAME` — Target sheet name within the spreadsheet
- `SHEETS_SERVICE_ACCOUNT_PATH` — Path to service account JSON

**Application Behavior:**
- `ATTACHMENT_EXTENSION` — File extension to process (default: `.txt`)
- `BATCH_SIZE` — Records per batch (default: `100`)
- `LOG_LEVEL` — Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)
- `LOG_FILE` — Log file path (default: `logs/gmail-to-sheets.log`)
- `SKIP_IF_DUPLICATE` — Skip duplicate files (default: `true`)
- `ARCHIVE_AFTER_PROCESS` — Move processed emails to archive (default: `true`)
- `TIMEZONE` — Application timezone (default: `Europe/Lisbon`)
- `ENABLE_MATCHING` — Enable matching logic (default: `false`)
- `ENABLE_TRANSFER` — Enable transfer to CONTAORDEM sheet (default: `true`)
- `UPDATE_EXISTING_ROWS` — Update existing rows if matching (default: `false`)

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

## Troubleshooting

### Common Issues

**Module Duplication in mypy**
- Issue: `Source file found twice under different module names`
- Solution: Already configured with `explicit_package_bases = true` in `pyproject.toml`
- Note: Type checking requires gradual migration to proper type hints

**Google API Authentication Failures**
- Verify credentials file paths are correct in `.env`
- Ensure Gmail API is enabled in Google Cloud Console
- Check that OAuth token has not expired (stored in `credentials/gmail-oauth-token.json`)

**Duplicate Email Processing**
- Enable `SKIP_IF_DUPLICATE=true` to use content hash deduplication
- Check `logs/gmail-to-sheets.log` for deduplication details

**Empty Google Sheets Results**
- Verify `SHEETS_SPREADSHEET_ID` and `SHEETS_SHEET_NAME` are correct
- Ensure service account has edit access to spreadsheet
- Check logs for API errors

**MT940 Parsing Errors**
- Verify file format is standard MT940 (`.txt`)
- Check that files contain expected fields (`:60:`, `:61:`, `:62:`)
- Review logs for specific parsing issues per transaction

### Known Limitations

1. **Type Checking** — mypy reports 46 known errors requiring structural refactoring
2. **Google Imports** — Google libraries lack type stubs; imports are allowed without type analysis
3. **Sequential Matching** — Matching logic operates per-day with numeric sequences; concurrent runs may cause conflicts

## Quality Assurance

### Tests
```bash
pytest -v               # Run all tests
pytest --cov           # With coverage report
```

### Code Quality
```bash
ruff check src/        # Lint check (all issues auto-fixed)
mypy src/             # Type checking (see Known Limitations)
```

Current status: ✓ Ruff passes | ✓ Pytest passes | ⚠ Mypy has 46 known errors

## Deployment

### Docker Support (Future)
- Application designed for containerization
- Credentials should be mounted as volumes in production

### Systemd Service (Future)
- Can be deployed as systemd timer for scheduled runs
- Logs should be redirected to systemd journal

### Production Checklist
- [ ] All credentials configured in `.env`
- [ ] Credentials files secured with proper permissions (600)
- [ ] Log directory writable and monitored
- [ ] Gmail label names configured correctly
- [ ] Sheets spreadsheet shared with service account
- [ ] Run initial test: `python -m pytest`
- [ ] Monitor logs: `tail -f logs/gmail-to-sheets.log`

## Documentation

- `AGENTS.md` — Permanent development rules
- `MATCHING_LOGIC.md` — Detailed matching and sequential numbering logic
- `.agents/skills/gmail-to-sheets/SKILL.md` — Development skill guide
- `docs/GMAIL_INVESTIGATION.md` — Gmail API investigation notes
- `docs/OAUTH_SETUP.md` — OAuth setup guide

## Contributing

1. Ensure tests pass: `pytest`
2. Run linters: `ruff check src/ --fix`
3. Gradually improve type hints
4. Document new features in comments

## License

MIT
