"""
Custom exceptions for the gmail-to-sheets application.
"""


class GmailToSheetsException(Exception):
    """Base exception for the application."""

    pass


class ConfigurationError(GmailToSheetsException):
    """Raised when configuration is invalid or missing."""

    pass


class AuthenticationError(GmailToSheetsException):
    """Raised when authentication fails."""

    pass


class GmailError(GmailToSheetsException):
    """Raised when Gmail API operations fail."""

    pass


class SheetsError(GmailToSheetsException):
    """Raised when Google Sheets API operations fail."""

    pass


class ProcessingError(GmailToSheetsException):
    """Raised when message/attachment processing fails."""

    pass


class ValidationError(GmailToSheetsException):
    """Raised when data validation fails."""

    pass
