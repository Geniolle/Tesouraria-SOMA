"""
Configuration management with environment variable validation.

Uses Pydantic for type-safe configuration loading and validation.
"""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class CashBalanceSettings(BaseSettings):
    """Cash balance update configuration."""

    update_enabled: bool = Field(True, alias="CASH_BALANCE_UPDATE_ENABLED")
    sheet_name: str = Field("GERENCIAR CAIXAS", alias="CASH_BALANCE_SHEET_NAME")
    account_label: str = Field("CAIXA ECONÔMICA MONTEPIO GERAL - CC", alias="CASH_BALANCE_ACCOUNT_LABEL")
    header_row: int = Field(1, alias="CASH_BALANCE_HEADER_ROW")
    row_offset: int = Field(1, alias="CASH_BALANCE_ROW_OFFSET")
    verify_after_write: bool = Field(True, alias="CASH_BALANCE_VERIFY_AFTER_WRITE")

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @field_validator("header_row", mode="before")
    @classmethod
    def validate_header_row(cls, v):
        """Validate header row is positive integer."""
        row = int(v)
        if row <= 0:
            raise ValueError("CASH_BALANCE_HEADER_ROW must be a positive integer")
        return row

    @field_validator("row_offset", mode="before")
    @classmethod
    def validate_row_offset(cls, v):
        """Validate row offset is positive integer."""
        offset = int(v)
        if offset <= 0:
            raise ValueError("CASH_BALANCE_ROW_OFFSET must be a positive integer")
        return offset


class VerboCafeSettings(BaseSettings):
    """Verbo Café process configuration.

    The Verbo Café source sheets (``VC_VENDAS`` and ``Financeiro``) live in a
    spreadsheet that is separate from the main treasury spreadsheet. The
    default keeps parity with the legacy Apps Script; override it through the
    ``VERBO_CAFE_SOURCE_SPREADSHEET_ID`` environment variable if needed.
    """

    source_spreadsheet_id: str = Field(
        "11sUHhTzKaV21uX_FpBOEnJxNpFjUn6EHEiU79Pe3jXU",
        alias="VERBO_CAFE_SOURCE_SPREADSHEET_ID",
    )
    vendas_sheet_name: str = Field(
        "VC_VENDAS",
        alias="VERBO_CAFE_VENDAS_SHEET_NAME",
    )
    pagamentos_sheet_name: str = Field(
        "Financeiro",
        alias="VERBO_CAFE_PAGAMENTOS_SHEET_NAME",
    )
    service_account_path: Path | None = Field(
        None,
        alias="VERBO_CAFE_SERVICE_ACCOUNT_PATH",
    )

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @field_validator("service_account_path", mode="before")
    @classmethod
    def _blank_path_to_none(cls, v):
        """Treat an empty ``VERBO_CAFE_SERVICE_ACCOUNT_PATH`` as unset.

        When unset, the process reuses the main Sheets service account.
        """
        if v is None or str(v).strip() == "":
            return None
        return Path(v)


class FaturasEmailRoute(BaseModel):
    """One sender -> Drive folder + Gmail label mapping for Faturas Email."""

    sender: str
    drive_folder_id: str
    label: str
    filename_token: str
    query: str | None = None
    attachment_ext: str | None = None

    def gmail_query(self) -> str:
        """Full Gmail query for this route (defaults to inbox + sender)."""
        return self.query or f"in:inbox from:{self.sender}"

    def resolved_ext(self, default_ext: str) -> str:
        """Attachment extension for this route, falling back to the default."""
        ext = (self.attachment_ext or default_ext or "").strip()
        if ext and not ext.startswith("."):
            ext = f".{ext}"
        return ext


class FaturasEmailSettings(BaseSettings):
    """Faturas Email process configuration.

    Saves email attachments into a Google Drive folder, then labels and
    archives the message. ``routes`` is a JSON array (see ``.env``); every
    entry is a :class:`FaturasEmailRoute`.
    """

    enabled: bool = Field(False, alias="FATURAS_EMAIL_ENABLED")
    attachment_ext: str = Field(".pdf", alias="FATURAS_EMAIL_ATTACHMENT_EXT")
    routes: list[FaturasEmailRoute] = Field(
        default_factory=list,
        alias="FATURAS_EMAIL_ROUTES",
    )

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }


class GmailSettings(BaseSettings):
    """Gmail-specific configuration."""

    account_email: str = Field(..., alias="GMAIL_ACCOUNT_EMAIL")
    sender_email: str = Field(..., alias="GMAIL_SENDER_EMAIL")
    search_query: str = Field(..., alias="GMAIL_SEARCH_QUERY")
    label_name: str = Field(..., alias="GMAIL_LABEL_NAME")
    backup_label_name: str = Field(..., alias="GMAIL_BACKUP_LABEL_NAME")
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
    cash_balance: CashBalanceSettings
    verbo_cafe: VerboCafeSettings
    faturas_email: FaturasEmailSettings
    attachment_extension: str = Field(".txt", alias="ATTACHMENT_EXTENSION")
    batch_size: int = Field(100, alias="BATCH_SIZE")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_file: str = Field("logs/gmail-to-sheets.log", alias="LOG_FILE")
    skip_if_duplicate: bool = Field(True, alias="SKIP_IF_DUPLICATE")
    archive_after_process: bool = Field(True, alias="ARCHIVE_AFTER_PROCESS")
    timezone: str = Field("Europe/Lisbon", alias="TIMEZONE")
    enable_matching: bool = Field(False, alias="ENABLE_MATCHING")
    enable_transfer: bool = Field(True, alias="ENABLE_TRANSFER")
    update_existing_rows: bool = Field(False, alias="UPDATE_EXISTING_ROWS")

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
        cash_balance_settings = CashBalanceSettings()
        verbo_cafe_settings = VerboCafeSettings()
        faturas_email_settings = FaturasEmailSettings()
        app_settings = AppSettings(
            gmail=gmail_settings,
            sheets=sheets_settings,
            cash_balance=cash_balance_settings,
            verbo_cafe=verbo_cafe_settings,
            faturas_email=faturas_email_settings,
        )
        return app_settings
    except Exception as e:
        raise RuntimeError(
            f"Failed to load configuration: {e}\n"
            f"Please ensure all required environment variables are set in .env file"
        ) from e
