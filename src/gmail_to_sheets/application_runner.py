"""
Application runner for CLI and scheduler orchestration.

Coordinates the 3 core business processes:
1. Extrato: Extract MT940 statement attachments from Gmail and write to T_EXTRATO & CONTAORDEM.
2. Entradas: Process manual tithe/offering entries from DÍZIMOS/OFERTAS to CONTAORDEM.
3. Conciliacao: Reconcile and match rows against CONTAORDEM and update DOC.SOMA.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.orchestrator import Orchestrator as ExtratoOrchestrator
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
        self.extrato_running = False
        self.entradas_running = False
        self.conciliacao_running = False
        self.gmail_client: GmailClient | None = None

    def run_extrato(self) -> None:
        """Run Extrato process (Gmail MT940 extraction to Google Sheets)."""
        if self.extrato_running:
            logger.warning("Extrato process already running, skipping this cycle")
            return

        self.extrato_running = True
        try:
            logger.info("=" * 80)
            logger.info("Starting Extrato process (Gmail MT940 Extraction)...")
            logger.info("=" * 80)

            orchestrator = ExtratoOrchestrator()
            orchestrator.run()

            logger.info("Extrato process completed successfully")
        except Exception as e:
            logger.error(f"Extrato process failed: {e}", exc_info=True)
        finally:
            self.extrato_running = False

    def run_entradas(self) -> None:
        """Run Entradas process (DÍZIMOS/OFERTAS to CONTAORDEM)."""
        if self.entradas_running:
            logger.warning("Entradas process already running, skipping this cycle")
            return

        self.entradas_running = True
        try:
            logger.info("=" * 80)
            logger.info("Starting Entradas process (DÍZIMOS/OFERTAS -> CONTAORDEM)...")
            logger.info("=" * 80)

            orchestrator = EntradasOrchestrator()
            orchestrator.run()

            logger.info("Entradas process completed successfully")
        except Exception as e:
            logger.error(f"Entradas process failed: {e}", exc_info=True)
        finally:
            self.entradas_running = False

    def run_conciliation(self, source_sheet: str = "T_EXTRATO") -> None:
        """Run Conciliacao process."""
        if self.conciliacao_running:
            logger.warning("Conciliacao process already running, skipping this cycle")
            return

        self.conciliacao_running = True
        try:
            logger.info("=" * 80)
            logger.info(f"Starting Conciliacao process for {source_sheet}...")
            logger.info("=" * 80)

            orchestrator = ConciliationOrchestrator(source_sheet=source_sheet)
            orchestrator.run()

            logger.info("Conciliacao process completed successfully")
        except Exception as e:
            logger.error(f"Conciliacao process failed: {e}", exc_info=True)
        finally:
            self.conciliacao_running = False

    def run_full_cycle(self) -> None:
        """Run all 3 processes in sequential order: Extrato -> Entradas -> Conciliação."""
        logger.info("=" * 80)
        logger.info("Executing FULL cycle (Extrato -> Entradas -> Conciliacao)...")
        logger.info("=" * 80)

        # 1. Extrato (reads Gmail, writes to T_EXTRATO & CONTAORDEM)
        self.run_extrato()

        # 2. Entradas (transfers validated entries to CONTAORDEM)
        self.run_entradas()

        # 3. Conciliacao (matches and reconciles against CONTAORDEM)
        self.run_conciliation(source_sheet="T_EXTRATO")

        logger.info("FULL cycle execution finished")

    def run_once(self) -> None:
        """Run full cycle once (for testing and manual triggers)."""
        try:
            self.run_full_cycle()
        except Exception as e:
            logger.error(f"Process execution failed: {e}")
            sys.exit(1)

    def run_extrato_once(self) -> None:
        """Run Extrato process once manually."""
        try:
            self.run_extrato()
        except Exception as e:
            logger.error(f"Extrato execution failed: {e}")
            sys.exit(1)

    def run_entradas_once(self) -> None:
        """Run Entradas process once manually."""
        try:
            self.run_entradas()
        except Exception as e:
            logger.error(f"Entradas execution failed: {e}")
            sys.exit(1)

    def run_conciliation_manual(self, source_sheet: str = "T_EXTRATO") -> None:
        """Run Conciliacao manually for a given source sheet."""
        try:
            self.run_conciliation(source_sheet=source_sheet)
        except Exception as e:
            logger.error(f"Conciliation process failed: {e}")
            sys.exit(1)

    def start_scheduler(self) -> None:
        """Start the background scheduler."""
        try:
            logger.info("Starting scheduler for Extrato, Entradas and Conciliacao processes...")

            self.scheduler.add_job(
                self.run_full_cycle,
                trigger=IntervalTrigger(minutes=2),
                id="full_cycle_job",
                name="Full pipeline cycle (Extrato -> Entradas -> Conciliacao every 2 minutes)",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

            self.scheduler.start()
            self.is_running = True

            logger.info("Scheduler started successfully")
            logger.info("=" * 80)
            logger.info("SCHEDULE:")
            logger.info("  Full Cycle: every 2 minutes")
            logger.info("  Sequence:   1. Extrato (Gmail MT940)")
            logger.info("              2. Entradas (Dízimos/Ofertas)")
            logger.info("              3. Conciliação (T_EXTRATO)")
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

    def authenticate_gmail(self) -> GmailClient:
        """Authenticate Gmail and cache the client."""
        if self.gmail_client is not None:
            return self.gmail_client

        authenticator = GmailAuthenticator(
            client_secrets_path=self.settings.gmail.client_secrets_path,
            credentials_path=self.settings.gmail.credentials_path,
        )
        credentials = authenticator.get_credentials()
        self.gmail_client = GmailClient(credentials)
        return self.gmail_client

    def check_inbox(self) -> list[dict[str, object]]:
        """
        Validate Gmail inbox without selecting, moving, or archiving messages.

        Returns:
            List of message summaries that matched the configured query.
        """
        logger.info("Running read-only inbox validation...")
        gmail_client = self.authenticate_gmail()

        message_ids = gmail_client.search_messages(
            query=self.settings.gmail.search_query,
            max_results=self.settings.batch_size,
        )

        if not message_ids:
            logger.info("No matching inbox messages found")
            print("No matching inbox messages found.")
            return []

        print(f"Found {len(message_ids)} matching inbox message(s).")
        summaries: list[dict[str, object]] = []

        for idx, message_id in enumerate(message_ids, start=1):
            message = gmail_client.get_message(message_id)
            payload = message.get("payload", {})
            headers = {
                str(header.get("name", "")).strip().lower(): str(header.get("value", "")).strip()
                for header in payload.get("headers", [])
                if header.get("name")
            }
            attachments = gmail_client.get_attachments(
                message_id,
                attachment_extension=self.settings.attachment_extension,
            )

            summary = {
                "message_id": message_id,
                "subject": headers.get("subject", ""),
                "from": headers.get("from", ""),
                "date": headers.get("date", ""),
                "attachments": [item["filename"] for item in attachments],
                "attachment_count": len(attachments),
            }
            summaries.append(summary)

            print(
                f"{idx}. {summary['subject'] or '(no subject)'} | "
                f"{summary['from'] or '(no sender)'} | "
                f"{summary['date'] or '(no date)'} | "
                f"attachments: {summary['attachment_count']}"
            )
            if summary["attachments"]:
                print(f"   files: {', '.join(summary['attachments'])}")

        logger.info("Read-only inbox validation completed")
        return summaries


def build_parser() -> argparse.ArgumentParser:
    """Build the application CLI parser."""
    parser = argparse.ArgumentParser(
        description="AppExtrato - Process Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.gmail_to_sheets.app run-scheduled              # Run scheduler (all processes every 2 min)
  python -m src.gmail_to_sheets.app run-once                   # Run full cycle once (Extrato + Entradas + Conciliação)
  python -m src.gmail_to_sheets.app extrato                    # Run Extrato only (Gmail MT940 download)
  python -m src.gmail_to_sheets.app entradas                   # Run Entradas only (Dízimos/Ofertas transfer)
  python -m src.gmail_to_sheets.app check-inbox                # Validate inbox only, no actions
  python -m src.gmail_to_sheets.app conciliacao T_EXTRATO      # Run Conciliation for T_EXTRATO
  python -m src.gmail_to_sheets.app status                     # Show scheduler status
        """,
    )

    parser.add_argument(
        "command",
        choices=[
            "run-scheduled",
            "run-once",
            "extrato",
            "entradas",
            "conciliacao",
            "check-inbox",
            "status",
        ],
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
        logger.info("Running full pipeline cycle once")
        app.run_once()
    elif args.command == "extrato":
        logger.info("Running Extrato process once (Gmail MT940 Extraction)")
        app.run_extrato_once()
    elif args.command == "entradas":
        logger.info("Running Entradas process once")
        app.run_entradas_once()
    elif args.command == "check-inbox":
        logger.info("Running read-only inbox validation")
        app.check_inbox()
    elif args.command == "conciliacao":
        logger.info(f"Running Conciliation process for {args.source_sheet}")
        app.run_conciliation_manual(source_sheet=args.source_sheet)
    elif args.command == "status":
        logger.info("Application ready")
        print("AppExtrato - Process Management System")
        print("  Processes:")
        print("    - Extrato:     Scheduled (Gmail MT940 Extraction -> T_EXTRATO & CONTAORDEM)")
        print("    - Entradas:    Scheduled (DÍZIMOS/OFERTAS -> CONTAORDEM)")
        print("    - Conciliacao: Scheduled (T_EXTRATO Reconciliation)")
        print("  Status: Ready")

    return 0


def main() -> int:
    """Program entrypoint for `python -m src.gmail_to_sheets.app`."""
    return run_cli()
