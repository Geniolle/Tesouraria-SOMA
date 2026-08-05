# Troubleshooting Guide

## Configuration Issues

### "Failed to load configuration: No environment variables found"

**Cause:** `.env` file is missing or not loaded correctly.

**Solution:**
1. Verify `.env` exists in project root: `ls -la .env`
2. Check all required variables are present: `grep -E "^(GMAIL_|SHEETS_)" .env`
3. Ensure no spaces around `=` in `.env` file
4. Restart application after `.env` changes

```bash
# Verify configuration loads
python -c "from src.gmail_to_sheets.config.settings import load_settings; print(load_settings())"
```

### "GMAIL_BACKUP_LABEL_NAME is mandatory"

**Cause:** Environment variable missing or settings not loading.

**Solution:**
```bash
# Add to .env:
GMAIL_BACKUP_LABEL_NAME=your-backup-label

# Verify it's loaded:
python -c "from src.gmail_to_sheets.config.settings import GmailSettings; print(GmailSettings().backup_label_name)"
```

---

## Gmail Authentication Issues

### "Authentication failed: No credentials found"

**Cause:** OAuth token expired or missing.

**Solution:**
1. Delete the token file: `rm credentials/gmail-oauth-token.json`
2. Next run will trigger OAuth flow in browser
3. Authorize access to your Gmail account

### "Insufficient permissions to access Gmail API"

**Cause:** OAuth scope or credentials incorrect.

**Solution:**
1. Verify `GMAIL_CLIENT_SECRETS_PATH` points to correct file
2. Check Google Cloud Console:
   - Go to APIs & Services > Enabled APIs
   - Ensure "Gmail API" is enabled
   - Check OAuth consent screen configuration
3. Delete cached token and re-authenticate

### "SCOPES mismatch error"

**Cause:** Token was created with different scopes.

**Solution:**
- Delete token: `rm credentials/gmail-oauth-token.json`
- Re-run application to create new token with correct scopes

---

## Google Sheets Issues

### "Spreadsheet not found" (404 error)

**Cause:** Invalid spreadsheet ID.

**Solution:**
1. Verify ID from Google Sheets URL: `docs.google.com/spreadsheets/d/**YOUR_ID**/edit`
2. Update `.env`: `SHEETS_SPREADSHEET_ID=YOUR_ID`
3. Restart application

### "Permission denied: Service account lacks access"

**Cause:** Service account not shared on spreadsheet.

**Solution:**
1. Find service account email in `credentials/sheets-service-account.json`: `client_email`
2. Open Google Sheets spreadsheet
3. Click Share > Add the service account email
4. Give "Editor" permissions

### "Sheet name not found" (gid mismatch)

**Cause:** Sheet name doesn't exist or was renamed.

**Solution:**
1. Verify sheet name in spreadsheet (bottom tabs)
2. Update `.env`: `SHEETS_SHEET_NAME=correct_sheet_name`
3. Ensure no typos or extra spaces

### "Range error when writing to sheet"

**Cause:** Sheet structure doesn't match expected columns.

**Solution:**
1. Verify headers in target sheet match expected format
2. Check logs for which column caused error: `tail -f logs/gmail-to-sheets.log`
3. Ensure "DOC. SOMA" and "DESCRIÇÃO SOMA" columns exist

---

## Email Processing Issues

### "No emails found matching search query"

**Cause:** Gmail search query returns no results.

**Solution:**
1. Test search manually in Gmail: Search box > `GMAIL_SEARCH_QUERY` value
2. Verify sender email exists and is correct: `GMAIL_SENDER_EMAIL`
3. Check that emails have `.txt` attachments (configurable via `ATTACHMENT_EXTENSION`)
4. Verify labels: emails must have `GMAIL_LABEL_NAME` label

### "Attachment parsing failed: Invalid MT940 format"

**Cause:** File is not valid MT940 format.

**Solution:**
1. Check file content for MT940 tags (`:60:`, `:61:`, `:62:`)
2. Verify encoding is UTF-8 or ASCII
3. Check for special characters that might break parsing
4. Review detailed error in logs: `grep "Failed to parse" logs/gmail-to-sheets.log`

### "Duplicate file detected, skipping"

**Cause:** File was already processed (when `SKIP_IF_DUPLICATE=true`).

**Solution:**
- This is expected behavior for idempotent processing
- To reprocess: Delete deduplication cache or update file content
- Or set `SKIP_IF_DUPLICATE=false` (not recommended)

---

## Performance Issues

### Application runs very slowly

**Cause:** Batch size too large or API rate limiting.

**Solution:**
1. Reduce batch size: `BATCH_SIZE=50` (default: 100)
2. Check Google API quotas in Cloud Console
3. Add delays between batches if rate-limited
4. Review logs for specific slow operations

### "Rate limit exceeded" (429 errors)

**Cause:** Too many API calls too quickly.

**Solution:**
1. Reduce `BATCH_SIZE` to 25-50
2. Add longer delays between runs if using cron
3. Check quota usage in Google Cloud Console
4. Contact Google Cloud support for quota increase

---

## Logging and Debugging

### Enable debug logging

```bash
# In .env:
LOG_LEVEL=DEBUG

# Or via environment:
LOG_LEVEL=DEBUG python -m src.gmail_to_sheets
```

### View recent errors

```bash
# Last 50 lines
tail -50 logs/gmail-to-sheets.log

# Filter for errors only
grep ERROR logs/gmail-to-sheets.log | tail -20

# Follow live logs
tail -f logs/gmail-to-sheets.log
```

### Export logs for analysis

```bash
# Last 24 hours
find logs/ -mtime -1 -type f -exec cat {} \; > logs_archive.txt

# Last 1000 lines with timestamps
tail -1000 logs/gmail-to-sheets.log > logs_backup.txt
```

---

## Testing and Validation

### Run unit tests

```bash
pytest tests/unit/ -v
```

### Run specific test

```bash
pytest tests/unit/test_config.py::TestGmailSettings -v
```

### Test with coverage

```bash
pytest --cov=src/ --cov-report=html
# Open htmlcov/index.html in browser
```

### Validate configuration without running

```bash
python -c "
from src.gmail_to_sheets.config.settings import load_settings
settings = load_settings()
print(f'Gmail: {settings.gmail.account_email}')
print(f'Sheets: {settings.sheets.spreadsheet_id}')
"
```

---

## Code Quality Issues

### Fix linting errors

```bash
ruff check src/ --fix
```

### Check type annotations

```bash
mypy src/
```

Note: mypy reports 46 known errors requiring structural refactoring. This is documented in README.md.

### Fix import ordering

```bash
ruff check src/ --select I --fix
```

---

## Production Issues

### Application crashes on startup

1. Check Python version: `python --version` (requires 3.10+)
2. Verify all dependencies: `pip check`
3. Review logs from startup: `logs/gmail-to-sheets.log`
4. Test configuration loads: `python -c "from src.gmail_to_sheets.config.settings import load_settings; load_settings()"`

### Memory issues with large attachments

1. Reduce `BATCH_SIZE`
2. Process in smaller time windows
3. Monitor available memory: `free -h`
4. Consider splitting into multiple runs

### Files corrupted after processing

1. Ensure atomic writes: Check `ARCHIVE_AFTER_PROCESS` setting
2. Verify disk space available: `df -h`
3. Check file permissions: `ls -la credentials/`
4. Review logs for write errors

---

## Getting Help

1. Check logs first: `tail logs/gmail-to-sheets.log`
2. Enable debug mode: `LOG_LEVEL=DEBUG`
3. Verify configuration: Run configuration validation test
4. Check recent git history: `git log --oneline -10`
5. Review MATCHING_LOGIC.md for complex behavior

