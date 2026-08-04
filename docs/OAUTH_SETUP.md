# OAuth 2.0 Setup Guide

This guide explains how to obtain Google OAuth credentials for Gmail and Google Sheets APIs.

## Gmail OAuth Setup (Desktop Application)

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Click "NEW PROJECT"
4. Enter project name: `gmail-to-sheets`
5. Click "CREATE"
6. Wait for the project to be created

### Step 2: Enable Gmail API

1. In the Google Cloud Console, search for "Gmail API"
2. Click on it
3. Click "ENABLE"
4. Wait for it to enable

### Step 3: Create OAuth 2.0 Credentials

1. In the sidebar, go to "Credentials"
2. Click "CREATE CREDENTIALS" → "OAuth 2.0 Client IDs"
3. You'll be prompted to create a consent screen first:
   - Click "CONFIGURE CONSENT SCREEN"
   - Choose "External" user type
   - Click "CREATE"
   - Fill in:
     - App name: `gmail-to-sheets`
     - User support email: (your email)
     - Developer contact: (your email)
   - Click "SAVE AND CONTINUE"
   - Skip scopes page, click "SAVE AND CONTINUE"
   - Skip test users page, click "SAVE AND CONTINUE"
   - Click "BACK TO DASHBOARD"

4. Go back to "Credentials" and click "CREATE CREDENTIALS" → "OAuth 2.0 Client IDs"
5. Choose "Desktop application"
6. Click "CREATE"
7. Click "DOWNLOAD JSON"
8. Save the file as `credentials/gmail-client-secret.json` in this project

### Step 4: Enable Google Sheets API

1. In the sidebar, search for "Google Sheets API"
2. Click on it
3. Click "ENABLE"

## Google Sheets Service Account Setup

A service account is used for authenticating with Google Sheets without user interaction.

### Step 1: Create a Service Account

1. In Google Cloud Console, go to "Service Accounts" (search in the top bar)
2. Click "CREATE SERVICE ACCOUNT"
3. Enter:
   - Service account name: `gmail-to-sheets-sa`
   - Click "CREATE AND CONTINUE"
4. Grant "Editor" role (temporary; we'll restrict it later)
5. Click "CONTINUE"
6. Click "CREATE KEY"
7. Choose "JSON"
8. Click "CREATE"
9. The JSON file will download automatically
10. Save it as `credentials/sheets-service-account.json` in this project

### Step 2: Share Your Spreadsheet

1. Open your Google Sheet in a web browser
2. Click "Share" (top right)
3. In the dialog, paste the service account email from the JSON file:
   - Open `credentials/sheets-service-account.json`
   - Find the value of `"client_email"`
   - Paste it in the Share dialog
4. Give it "Editor" permissions
5. Click "Share"

## Configuration

### 1. Create `.env` file

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### 2. Update `.env` with your values

```
GMAIL_ACCOUNT_EMAIL=verbodavidabraga@gmail.com
GMAIL_SENDER_EMAIL=noreply@montepio.pt
GMAIL_SEARCH_QUERY=in:inbox from:noreply@montepio.pt has:attachment
GMAIL_LABEL_NAME=Serviços/Banco/Montepio24/MT940
GMAIL_CREDENTIALS_PATH=credentials/gmail-oauth-token.json
GMAIL_CLIENT_SECRETS_PATH=credentials/gmail-client-secret.json

SHEETS_SPREADSHEET_ID=<your-spreadsheet-id>
SHEETS_SHEET_NAME=Transactions
SHEETS_SERVICE_ACCOUNT_PATH=credentials/sheets-service-account.json
```

### 3. Get Your Spreadsheet ID

1. Open your Google Sheet
2. Look at the URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`
3. Copy the `SPREADSHEET_ID` part
4. Paste it in `.env` as `SHEETS_SPREADSHEET_ID`

## Testing

Once configured, the application will:

1. **On first run**, open your browser for Gmail OAuth approval
2. **Store the token** in `credentials/gmail-oauth-token.json` for future use
3. **Use the service account** to authenticate with Google Sheets (no browser needed)

## Security Notes

- ✓ `.gitignore` protects all credential files
- ✓ `.env` is listed in `.gitignore` (never commit it)
- ✓ Never share OAuth tokens or service account keys
- ✓ Credential files are local-only; they won't be uploaded to GitHub

## Troubleshooting

**"credentials/gmail-client-secret.json not found"**
- Download the OAuth credentials from Google Cloud Console
- Save exactly as `credentials/gmail-client-secret.json`

**"The caller does not have permission to perform..."**
- Ensure the service account has Editor permissions on the Google Sheet
- Check that the email in `.env` is correct

**"Invalid Spreadsheet ID"**
- Verify the `SHEETS_SPREADSHEET_ID` is correct
- Make sure the sheet is not in trash
- Confirm the service account has access to it
