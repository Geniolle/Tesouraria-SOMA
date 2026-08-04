"""
Exceptions for MT940 parsing and validation.
"""


class MT940ParseError(Exception):
    """Base exception for MT940 parsing errors."""

    pass


class MT940InvalidFormat(MT940ParseError):
    """Raised when MT940 format is invalid."""

    pass


class MT940MissingSection(MT940ParseError):
    """Raised when required MT940 section is missing."""

    def __init__(self, section: str):
        super().__init__(f"Missing required section: {section}")


class MT940InvalidDate(MT940ParseError):
    """Raised when date format is invalid."""

    def __init__(self, date_str: str, format_str: str):
        super().__init__(f"Invalid date '{date_str}' (expected {format_str})")


class MT940InvalidAmount(MT940ParseError):
    """Raised when amount format is invalid."""

    def __init__(self, amount_str: str):
        super().__init__(f"Invalid amount format: {amount_str}")


class TransactionValidationError(Exception):
    """Raised when transaction data fails validation."""

    def __init__(self, field: str, value: str, reason: str):
        super().__init__(f"Invalid {field}: {value} ({reason})")


class DeduplicationError(Exception):
    """Raised when duplicate transaction is detected."""

    def __init__(self, dedup_key: str):
        super().__init__(f"Duplicate transaction detected: {dedup_key}")
