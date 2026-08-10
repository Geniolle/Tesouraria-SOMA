"""
Logging configuration for the application.

Sets up structured logging to file and console with automatic rotation.
"""

import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_file: str, log_level: str) -> None:
    """
    Configure logging for the application.

    Args:
        log_file: Path to log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_format = (
        "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"
    )

    root_logger = logging.getLogger()

    # Clear existing handlers to avoid duplicates when setup_logging is called multiple times
    root_logger.handlers.clear()

    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Rotating file handler: 50MB max, keep 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_path),
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=5
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(logging.Formatter(log_format))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(logging.Formatter(log_format))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    root_logger.info(f"Logging initialized: level={log_level}, file={log_path}, max_size=50MB")
