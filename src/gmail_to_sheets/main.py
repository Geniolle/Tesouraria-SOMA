"""
Entry point for the gmail-to-sheets application.
"""

import logging
import sys

from src.gmail_to_sheets.exceptions.application import GmailToSheetsException
from src.gmail_to_sheets.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def main() -> int:
    """
    Start the application.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        orchestrator = Orchestrator()
        orchestrator.run()
        return 0
    except GmailToSheetsException as e:
        print(f"Application error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
