"""
Entry point for the gmail-to-sheets application.
"""

from src.gmail_to_sheets.orchestrator import Orchestrator


def main() -> None:
    """Start the application."""
    orchestrator = Orchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
