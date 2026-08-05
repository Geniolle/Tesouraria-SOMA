"""
Unit tests for configuration management.
"""

from pathlib import Path

from src.gmail_to_sheets.config.settings import GmailSettings, SheetsSettings


class TestGmailSettings:
    """Tests for Gmail configuration."""

    def test_gmail_settings_loads_from_env(self, monkeypatch):
        """Test that Gmail settings load environment variables."""
        monkeypatch.setenv("GMAIL_ACCOUNT_EMAIL", "test@gmail.com")
        monkeypatch.setenv("GMAIL_SENDER_EMAIL", "sender@example.com")
        monkeypatch.setenv("GMAIL_SEARCH_QUERY", "test query")
        monkeypatch.setenv("GMAIL_LABEL_NAME", "Test/Label")
        monkeypatch.setenv("GMAIL_BACKUP_LABEL_NAME", "Test/Backup")
        monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", "/tmp/creds.json")
        monkeypatch.setenv("GMAIL_CLIENT_SECRETS_PATH", "/tmp/secret.json")

        settings = GmailSettings()

        assert settings.account_email == "test@gmail.com"
        assert settings.sender_email == "sender@example.com"
        assert settings.search_query == "test query"
        assert settings.label_name == "Test/Label"
        assert settings.backup_label_name == "Test/Backup"
        assert isinstance(settings.credentials_path, Path)
        assert isinstance(settings.client_secrets_path, Path)

    def test_gmail_settings_validates_backup_label(self, monkeypatch):
        """Test that backup_label_name is properly loaded from env."""
        monkeypatch.setenv("GMAIL_ACCOUNT_EMAIL", "test@gmail.com")
        monkeypatch.setenv("GMAIL_SENDER_EMAIL", "sender@example.com")
        monkeypatch.setenv("GMAIL_SEARCH_QUERY", "test query")
        monkeypatch.setenv("GMAIL_LABEL_NAME", "Test/Label")
        monkeypatch.setenv("GMAIL_BACKUP_LABEL_NAME", "Test/Backup/Label")
        monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", "/tmp/creds.json")
        monkeypatch.setenv("GMAIL_CLIENT_SECRETS_PATH", "/tmp/secret.json")

        settings = GmailSettings()
        assert settings.backup_label_name == "Test/Backup/Label"


class TestSheetsSettings:
    """Tests for Google Sheets configuration."""

    def test_sheets_settings_loads_from_env(self, monkeypatch):
        """Test that Sheets settings load environment variables."""
        monkeypatch.setenv("SHEETS_SPREADSHEET_ID", "sheet-123")
        monkeypatch.setenv("SHEETS_SHEET_NAME", "Transactions")
        monkeypatch.setenv("SHEETS_SERVICE_ACCOUNT_PATH", "/tmp/service.json")

        settings = SheetsSettings()

        assert settings.spreadsheet_id == "sheet-123"
        assert settings.sheet_name == "Transactions"
        assert isinstance(settings.service_account_path, Path)
