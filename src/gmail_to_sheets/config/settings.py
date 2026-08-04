"""
Configuration management with environment variable validation.

Uses Pydantic for type-safe configuration loading and validation.
"""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class GmailSettings(BaseSettings):
    """Gmail-specific configuration."""

    account_email: str = Field(..., alias="GMAIL_ACCOUNT_EMAIL")
    sender_email: str = Field(..., alias="GMAIL_SENDER_EMAIL")
    search_query: str = Field(..., alias="GMAIL_SEARCH_QUERY")
    label_name: str = Field(..., alias="GMAIL_LABEL_NAME")
    credentials_path: Path = Field(..., alias="GMAIL_CREDENTIALS_PATH")
    client_secrets_path: Path = Field(..., alias="GMAIL_CLIENT_SECRETS_PATH")

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @field_validator("credentials_path", "client_secrets_path", mode="before")
    @classmethod
    def validate_paths(cls, v: str) -> Path:
        """Convert string paths to Path objects."""
        return Path(v)


class SheetsSettings(BaseSettings):
    """Google Sheets-specific configuration."""

    spreadsheet_id: str = Field(..., alias="SHEETS_SPREADSHEET_ID")
    sheet_name: str = Field(..., alias="SHEETS_SHEET_NAME")
    service_account_path: Path = Field(..., alias="SHEETS_SERVICE_ACCOUNT_PATH")

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @field_validator("service_account_path", mode="before")
    @classmethod
    def validate_path(cls, v: str) -> Path:
        """Convert string path to Path object."""
        return Path(v)


class AppSettings(BaseSettings):
    """Global application configuration."""

    gmail: GmailSettings
    sheets: SheetsSettings
    attachment_extension: str = Field(".txt", alias="ATTACHMENT_EXTENSION")
    batch_size: int = Field(100, alias="BATCH_SIZE")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_file: str = Field("logs/gmail-to-sheets.log", alias="LOG_FILE")
    skip_if_duplicate: bool = Field(True, alias="SKIP_IF_DUPLICATE")
    archive_after_process: bool = Field(True, alias="ARCHIVE_AFTER_PROCESS")
    timezone: str = Field("Europe/Lisbon", alias="TIMEZONE")
    enable_matching: bool = Field(False, alias="ENABLE_MATCHING")
    enable_transfer: bool = Field(True, alias="ENABLE_TRANSFER")

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @field_validator("log_file", mode="before")
    @classmethod
    def validate_log_file(cls, v: str) -> str:
        """Ensure log directory exists."""
        log_path = Path(v)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return v


def load_settings() -> AppSettings:
    """Load and validate configuration from environment."""
    try:
        gmail_settings = GmailSettings()
        sheets_settings = SheetsSettings()
        app_settings = AppSettings(gmail=gmail_settings, sheets=sheets_settings)
        return app_settings
    except Exception as e:
        raise RuntimeError(
            f"Failed to load configuration: {e}\n"
            f"Please ensure all required environment variables are set in .env file"
        ) from e
