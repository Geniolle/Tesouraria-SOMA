"""
Logging configuration for the application.

Sets up structured logging to file and console.
"""

import logging
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

    # File handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(logging.Formatter(log_format))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(logging.Formatter(log_format))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    root_logger.info(f"Logging initialized: level={log_level}, file={log_path}")
