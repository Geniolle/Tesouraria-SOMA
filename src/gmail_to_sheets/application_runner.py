"""
Application runner for CLI and scheduler orchestration.

Keeps bootstrapping separate from process-specific business logic.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.conciliacao.orchestrator import ConciliationOrchestrator
from src.gmail_to_sheets.processes.entradas.orchestrator import EntradasOrchestrator

logger = logging.getLogger(__name__)


class AppRunner:
    """Coordinates scheduled and manual execution of application processes."""

    def __init__(self) -> None:
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.entradas_running = False

    def run_entradas(self) -> None:
        """Run Entradas process with a concurrency guard."""
        if self.entradas_running:
            logger.warning("Entradas process already running, skipping this cycle")
            return

        self.entradas_running = True
        try:
            logger.info("=" * 80)
            logger.info("Scheduled Entradas process starting...")
            logger.info("=" * 80)

            orchestrator = EntradasOrchestrator()
            orchestrator.run()

            logger.info("Scheduled Entradas process completed successfully")
            logger.info("Entradas finished, Conciliacao can now run")
        except Exception as e:
            logger.error(f"Scheduled Entradas process failed: {e}", exc_info=True)
        finally:
            self.entradas_running = False

    def run_conciliation(self) -> None:
        """Run Conciliacao process, waiting for Entradas if needed."""
        max_wait = 120
        waited = 0
        while self.entradas_running and waited < max_wait:
            logger.info("Waiting for Entradas to finish before starting Conciliacao...")
            time.sleep(5)
            waited += 5

        if self.entradas_running:
            logger.warning("Entradas still running after 2 minutes, skipping Conciliacao this cycle")
            return

        try:
            logger.info("=" * 80)
            logger.info("Scheduled Conciliacao process starting...")
            logger.info("=" * 80)

            orchestrator = ConciliationOrchestrator(source_sheet="T_EXTRATO")
            orchestrator.run()

            logger.info("Scheduled Conciliacao process completed successfully")
        except Exception as e:
            logger.error(f"Scheduled Conciliacao process failed: {e}", exc_info=True)

    def run_entradas_once(self) -> None:
        """Run Entradas process once."""
        try:
            logger.info("Running Entradas process once...")
            self.run_entradas()
        except Exception as e:
            logger.error(f"Process failed: {e}")
            sys.exit(1)

    def run_conciliation_manual(self, source_sheet: str = "T_EXTRATO") -> None:
        """Run Conciliacao manually for a given source sheet."""
        try:
            logger.info(f"Running Conciliation process ({source_sheet})...")
            orchestrator = ConciliationOrchestrator(source_sheet=source_sheet)
            orchestrator.run()
        except Exception as e:
            logger.error(f"Conciliation process failed: {e}")
            sys.exit(1)

    def start_scheduler(self) -> None:
        """Start the background scheduler."""
        try:
            logger.info("Starting scheduler for Entradas and Conciliacao processes...")

            self.scheduler.add_job(
                self.run_entradas,
                trigger=IntervalTrigger(minutes=2),
                id="entradas_job",
                name="Entradas process (every 2 minutes)",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

            self.scheduler.add_job(
                self.run_conciliation,
                trigger=IntervalTrigger(minutes=2, seconds=30),
                id="conciliacao_job",
                name="Conciliacao process (every 2 minutes, sequential after Entradas)",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

            self.scheduler.start()
            self.is_running = True

            logger.info("Scheduler started successfully")
            logger.info("=" * 80)
            logger.info("SCHEDULE:")
            logger.info("  Entradas:   every 2 minutes (0:00, 2:00, 4:00...)")
            logger.info("  Conciliacao: every 2 minutes (1:30, 3:30, 5:30...)")
            logger.info("  Strategy: Sequential (Conciliacao waits for Entradas)")
            logger.info("  Max wait: 2 minutes (skip if Entradas not done)")
            logger.info("=" * 80)
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

    def stop_scheduler(self) -> None:
        """Stop the background scheduler gracefully."""
        try:
            if self.is_running and self.scheduler.running:
                logger.info("Stopping scheduler...")
                self.scheduler.shutdown(wait=True)
                self.is_running = False
                logger.info("Scheduler stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

    def run_interactive(self) -> None:
        """Run scheduler interactively with signal handlers."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self.stop_scheduler()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.start_scheduler()
            logger.info("Application running. Press Ctrl+C to stop.")

            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop_scheduler()
            sys.exit(0)
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
            self.stop_scheduler()
            sys.exit(1)

    def run_once(self) -> None:
        """Run Entradas once."""
        try:
            logger.info("Running Entradas process once...")
            self.run_entradas()
        except Exception as e:
            logger.error(f"Process failed: {e}")
            sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Build the application CLI parser."""
    parser = argparse.ArgumentParser(
        description="AppExtrato - Process Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.gmail_to_sheets.app run-scheduled              # Run scheduler (every 2 min)
  python -m src.gmail_to_sheets.app run-once                   # Run Entradas once (for testing)
  python -m src.gmail_to_sheets.app conciliacao T_EXTRATO      # Run Conciliation for T_EXTRATO
  python -m src.gmail_to_sheets.app status                     # Show scheduler status
        """,
    )

    parser.add_argument(
        "command",
        choices=["run-scheduled", "run-once", "conciliacao", "status"],
        help="Command to execute",
    )

    parser.add_argument(
        "source_sheet",
        nargs="?",
        default="T_EXTRATO",
        help="Source sheet for conciliacao command (default: T_EXTRATO)",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Run the CLI entrypoint."""
    args = build_parser().parse_args(argv)
    app = AppRunner()

    if args.command == "run-scheduled":
        logger.info("Starting application with automatic scheduler")
        app.run_interactive()
    elif args.command == "run-once":
        logger.info("Running Entradas process once")
        app.run_once()
    elif args.command == "conciliacao":
        logger.info(f"Running Conciliation process for {args.source_sheet}")
        app.run_conciliation_manual(source_sheet=args.source_sheet)
    elif args.command == "status":
        logger.info("Application ready")
        print("AppExtrato - Process Management System")
        print("  Processes:")
        print("    - Entradas: Scheduled (every 2 minutes)")
        print("    - Conciliacao: Scheduled (every 2 minutes, +1:30s offset, waits for Entradas)")
        print("  Status: Ready")

    return 0


def main() -> int:
    """Program entrypoint for `python -m src.gmail_to_sheets.app`."""
    return run_cli()
