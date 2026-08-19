"""Compatibility wrapper for the application CLI runner."""

from src.gmail_to_sheets.application_runner import AppRunner, main, run_cli

AppOrchestrator = AppRunner

__all__ = ["AppRunner", "AppOrchestrator", "main", "run_cli"]


if __name__ == "__main__":
    raise SystemExit(main())
