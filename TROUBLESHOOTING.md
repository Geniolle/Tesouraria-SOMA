# Troubleshooting

## Configuration

### Failed to load configuration

Check that `.env` exists and contains the required `GMAIL_` and `SHEETS_` variables.

```bash
python -c "from src.gmail_to_sheets.config.settings import load_settings; print(load_settings())"
```

## Gmail Authentication

### Token missing or expired

Delete the cached token and re-authenticate.

```bash
rm credentials/gmail-oauth-token.json
```

### Headless server browser error

On the production server, the OAuth flow must work without a local browser.

## Google Sheets

### Spreadsheet or sheet name not found

Check `SHEETS_SPREADSHEET_ID` and `SHEETS_SHEET_NAME`.

### Permission denied

Share the spreadsheet with the service account email from `credentials/sheets-service-account.json`.

### Missing output columns

Confirm that `DOC. SOMA` and `DESCRICAO SOMA` exist in the target sheet.

## Validation

```bash
pytest tests/unit/
ruff check src/
python -m src.gmail_to_sheets.app run-once
```
