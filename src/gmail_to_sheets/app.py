"""
Main Application Orchestrator

Manages both Extrato and Entradas processes with scheduled execution.
- Extrato: Manual trigger (one-shot via CLI)
- Entradas: Automatic scheduled (every 1 minute)
"""

import logging
import signal
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.processes.entradas.orchestrator import EntradasOrchestrator
from src.gmail_to_sheets.processes.conciliacao.orchestrator import ConciliationOrchestrator

logger = logging.getLogger(__name__)


class AppOrchestrator:
    """Main application orchestrator."""

    def __init__(self):
        """Initialize app orchestrator."""
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.scheduler = BackgroundScheduler()
        self.is_running = False

    def run_entradas(self) -> None:
        """Run Entradas process (scheduled)."""
        try:
            logger.info("=" * 80)
            logger.info("Scheduled Entradas process starting...")
            logger.info("=" * 80)

            orchestrator = EntradasOrchestrator()
            orchestrator.run()

            logger.info("Scheduled Entradas process completed successfully")

        except Exception as e:
            logger.error(f"Scheduled Entradas process failed: {e}", exc_info=True)
            # Don't re-raise - scheduler should continue

    def start_scheduler(self) -> None:
        """Start background scheduler for Entradas and Conciliacao (every 1 minute)."""
        try:
            logger.info("Starting scheduler for Entradas and Conciliacao processes...")

            # Schedule Entradas to run every 1 minute
            self.scheduler.add_job(
                self.run_entradas,
                trigger=IntervalTrigger(minutes=1),
                id="entradas_job",
                name="Entradas process (every 1 minute)",
                replace_existing=True,
                max_instances=1  # Only one instance at a time
            )

            # Schedule Conciliacao to run every 1 minute (after Entradas)
            self.scheduler.add_job(
                self.run_conciliation,
                trigger=IntervalTrigger(minutes=1, seconds=30),
                id="conciliacao_job",
                name="Conciliacao process (every 1 minute, offset)",
                replace_existing=True,
                max_instances=1  # Only one instance at a time
            )

            self.scheduler.start()
            self.is_running = True

            logger.info("Scheduler started successfully")
            logger.info("Entradas process will run every 1 minute")
            logger.info("Conciliacao process will run every 1 minute (offset by 30 seconds)")

        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

    def stop_scheduler(self) -> None:
        """Stop background scheduler gracefully."""
        try:
            if self.is_running and self.scheduler.running:
                logger.info("Stopping scheduler...")
                self.scheduler.shutdown(wait=True)
                self.is_running = False
                logger.info("Scheduler stopped successfully")

        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

    def run_interactive(self) -> None:
        """Run scheduler in interactive mode (with signal handlers)."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self.stop_scheduler()
            sys.exit(0)

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.start_scheduler()
            logger.info("Application running. Press Ctrl+C to stop.")

            # Keep the application running
            while True:
                signal.pause()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop_scheduler()
            sys.exit(0)

        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
            self.stop_scheduler()
            sys.exit(1)

    def run_once(self) -> None:
        """Run Entradas process once (for testing)."""
        try:
            logger.info("Running Entradas process once...")
            self.run_entradas()

        except Exception as e:
            logger.error(f"Process failed: {e}")
            sys.exit(1)

    def run_conciliation(self) -> None:
        """Run Conciliation process (scheduled)."""
        try:
            logger.info("Running Conciliation process...")
            orchestrator = ConciliationOrchestrator(source_sheet="T_EXTRATO")
            orchestrator.run()

        except Exception as e:
            logger.error(f"Scheduled Conciliation process failed: {e}", exc_info=True)
            # Don't re-raise - scheduler should continue

    def run_conciliation_manual(self, source_sheet: str = "T_EXTRATO") -> None:
        """Run Conciliation process (manual trigger)."""
        try:
            logger.info(f"Running Conciliation process ({source_sheet})...")
            orchestrator = ConciliationOrchestrator(source_sheet=source_sheet)
            orchestrator.run()

        except Exception as e:
            logger.error(f"Conciliation process failed: {e}")
            sys.exit(1)


def main():
    """Entry point for application."""
    import argparse

    parser = argparse.ArgumentParser(
        description="AppExtrato - Process Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.gmail_to_sheets.app run-scheduled              # Run scheduler (every 1 min)
  python -m src.gmail_to_sheets.app run-once                   # Run Entradas once (for testing)
  python -m src.gmail_to_sheets.app conciliacao T_EXTRATO      # Run Conciliation for T_EXTRATO
  python -m src.gmail_to_sheets.app status                     # Show scheduler status
        """
    )

    parser.add_argument(
        "command",
        choices=["run-scheduled", "run-once", "conciliacao", "status"],
        help="Command to execute"
    )

    parser.add_argument(
        "source_sheet",
        nargs="?",
        default="T_EXTRATO",
        help="Source sheet for conciliacao command (default: T_EXTRATO)"
    )

    args = parser.parse_args()

    app = AppOrchestrator()

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
        print("    - Entradas: Scheduled (every 1 minute)")
        print("    - Conciliacao: Manual trigger")
        print("  Status: Ready")


if __name__ == "__main__":
    main()
