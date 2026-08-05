# Quick Start Guide

## 5-Minute Setup

### 1. Clone and Setup
```bash
cd gmail-to-sheets
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure Credentials
```bash
# Google Cloud Console setup
# 1. Create OAuth app → Download client secret
# 2. Create service account → Download JSON
# 3. Enable Gmail API and Sheets API

cp .env.example .env
# Edit .env with:
# - Your Gmail address
# - Spreadsheet ID from Google Sheets URL
# - Credential file paths
```

### 3. Place Credential Files
```bash
mkdir -p credentials
# Copy your downloaded files:
cp path/to/gmail-client-secret.json credentials/
cp path/to/sheets-service-account.json credentials/
```

### 4. Test Configuration
```bash
python -c "from src.gmail_to_sheets.config.settings import load_settings; load_settings()"
# No error = success!
```

### 5. Run Application
```bash
python -m src.gmail_to_sheets
```

First run will open browser for Gmail authentication.

---

## Common First-Run Issues

| Issue | Solution |
|-------|----------|
| "No environment variables" | Check `.env` exists and is in project root |
| "Can't find credentials" | Verify file paths in `.env` match actual locations |
| "Browser OAuth not opening" | Open link manually from console output |
| "Permission denied on Sheets" | Share spreadsheet with service account email |

---

## Verify It Works

### Check logs
```bash
tail -20 logs/gmail-to-sheets.log
```

### Look for success message
```
Starting gmail-to-sheets pipeline
Searched X emails
Parsed X transactions
Wrote X rows to Sheets
```

---

## Next Steps

- **Read full README:** `README.md`
- **Configure scheduling:** See `DEPLOYMENT.md`
- **Understand logic:** See `MATCHING_LOGIC.md` and `ARCHITECTURE.md`
- **Troubleshooting:** See `TROUBLESHOOTING.md`

---

## Key Environment Variables

```bash
# Gmail
GMAIL_ACCOUNT_EMAIL=your@gmail.com
GMAIL_SEARCH_QUERY=from:noreply@montepio.pt has:attachment

# Sheets
SHEETS_SPREADSHEET_ID=1poVWJGSBb13_... (from URL)
SHEETS_SHEET_NAME=MySheet

# Paths
GMAIL_CREDENTIALS_PATH=credentials/gmail-oauth-token.json
GMAIL_CLIENT_SECRETS_PATH=credentials/gmail-client-secret.json
SHEETS_SERVICE_ACCOUNT_PATH=credentials/sheets-service-account.json
```

---

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src/

# Specific test
pytest tests/unit/test_config.py
```

---

## Useful Commands

```bash
# Check code quality
ruff check src/

# See application version
python -m src.gmail_to_sheets --version

# Dry run (would display what would happen)
LOG_LEVEL=DEBUG python -m src.gmail_to_sheets

# View raw logs
tail -f logs/gmail-to-sheets.log
```

---

## Need Help?

1. Check `TROUBLESHOOTING.md` for your issue
2. Enable debug: `LOG_LEVEL=DEBUG` in `.env`
3. Check logs: `tail -f logs/gmail-to-sheets.log`
4. Review configuration: See `README.md` Configuration section

