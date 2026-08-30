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

from src.gmail_to_sheets.clients.gmail_auth import GmailAuthenticator
from src.gmail_to_sheets.clients.gmail_client import GmailClient
from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging
from src.gmail_to_sheets.orchestration import CentralOrchestrator
from src.gmail_to_sheets.orchestrator import Orchestrator as ExtratoOrchestrator
from src.gmail_to_sheets.processes.conciliacao.orchestrator import ConciliationOrchestrator
from src.gmail_to_sheets.processes.entradas.orchestrator import EntradasOrchestrator
from src.gmail_to_sheets.processes.saidas.orchestrator import SaidasOrchestrator

logger = logging.getLogger(__name__)


class AppRunner:
    """Coordinates scheduled and manual execution of application processes."""

    def __init__(self) -> None:
        self.settings = load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.central_orchestrator = CentralOrchestrator(settings=self.settings)
        self.scheduler = self.central_orchestrator.scheduler
        self.is_running = False
        self.gmail_client: GmailClient | None = None

    def run_extrato(self) -> None:
        """Run Extrato process (Gmail MT940 extraction to Google Sheets)."""
        try:
            logger.info("=" * 80)
            logger.info("Starting Extrato process (Gmail MT940 Extraction)...")
            logger.info("=" * 80)

            orchestrator = ExtratoOrchestrator(
                settings=self.settings,
                gmail_client=self.central_orchestrator.context.get_gmail_client(),
                sheets_client=self.central_orchestrator.context.get_sheets_client(),
            )
            orchestrator.run()

            logger.info("Extrato process completed successfully")
        except Exception as e:
            logger.error(f"Extrato process failed: {e}", exc_info=True)

    def run_entradas(self) -> None:
        """Run Entradas process (DÍZIMOS/OFERTAS to CONTAORDEM)."""
        try:
            logger.info("=" * 80)
            logger.info("Starting Entradas process (DÍZIMOS/OFERTAS -> CONTAORDEM)...")
            logger.info("=" * 80)

            orchestrator = EntradasOrchestrator(
                settings=self.settings,
                sheets_client=self.central_orchestrator.context.get_sheets_client(),
            )
            orchestrator.run()

            logger.info("Entradas process completed successfully")
        except Exception as e:
            logger.error(f"Entradas process failed: {e}", exc_info=True)

    def run_saidas(self) -> None:
        """Run SAÍDAS -> CONTAORDEM process."""
        try:
            logger.info("=" * 80)
            logger.info("Starting SAÍDAS process (SAÍDAS -> CONTAORDEM)...")
            logger.info("=" * 80)

            orchestrator = SaidasOrchestrator(
                settings=self.settings,
                sheets_client=self.central_orchestrator.context.get_sheets_client(),
            )
            orchestrator.run()

            logger.info("SAÍDAS process completed successfully")
        except Exception as e:
            logger.error(f"SAÍDAS process failed: {e}", exc_info=True)

    def run_conciliation(self, source_sheet: str = "T_EXTRATO") -> None:
        """Run Conciliacao process."""
        try:
            logger.info("=" * 80)
            logger.info(f"Starting Conciliacao process for {source_sheet}...")
            logger.info("=" * 80)

            orchestrator = ConciliationOrchestrator(
                source_sheet=source_sheet,
                settings=self.settings,
                sheets_client=self.central_orchestrator.context.get_sheets_client(),
            )
            orchestrator.run()

            logger.info("Conciliacao process completed successfully")
        except Exception as e:
            logger.error(f"Conciliacao process failed: {e}", exc_info=True)

    def run_tick(self) -> object:
        """Run one intelligent orchestration tick."""
        return self.central_orchestrator.run_tick()

    def run_once(self) -> None:
        """Run one orchestration tick once (for testing and manual triggers)."""
        try:
            self.run_tick()
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

    def run_saidas_once(self) -> None:
        """Run SAÍDAS process once manually."""
        try:
            self.run_saidas()
        except Exception as e:
            logger.error(f"SAÍDAS execution failed: {e}")
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
            self.central_orchestrator.start_scheduler()
            self.scheduler = self.central_orchestrator.scheduler
            self.is_running = self.central_orchestrator.is_running
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

    def stop_scheduler(self) -> None:
        """Stop the background scheduler gracefully."""
        try:
            self.central_orchestrator.stop_scheduler()
            self.is_running = self.central_orchestrator.is_running
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

    def status_lines(self) -> list[str]:
        """Return static status text without contacting external services."""
        return self.central_orchestrator.status_lines()


def build_parser() -> argparse.ArgumentParser:
    """Build the application CLI parser."""
    parser = argparse.ArgumentParser(
        description="AppExtrato - Process Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.gmail_to_sheets.app run-scheduled              # Run central scheduler (every 60 seconds)
  python -m src.gmail_to_sheets.app run-once                   # Run one orchestration tick
  python -m src.gmail_to_sheets.app extrato                    # Run Extrato only (Gmail MT940 download)
  python -m src.gmail_to_sheets.app entradas                   # Backward-compatible Dízimos/Ofertas command
  python -m src.gmail_to_sheets.app dizimos-ofertas            # Run Dízimos/Ofertas transfer
  python -m src.gmail_to_sheets.app saidas                     # Run SAÍDAS transfer
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
            "dizimos-ofertas",
            "saidas",
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
        logger.info("Running one orchestration tick")
        app.run_once()
    elif args.command == "extrato":
        logger.info("Running Extrato process once (Gmail MT940 Extraction)")
        app.run_extrato_once()
    elif args.command in {"entradas", "dizimos-ofertas"}:
        logger.info("Running Dízimos/Ofertas process once")
        app.run_entradas_once()
    elif args.command == "saidas":
        logger.info("Running SAÍDAS process once")
        app.run_saidas_once()
    elif args.command == "check-inbox":
        logger.info("Running read-only inbox validation")
        app.check_inbox()
    elif args.command == "conciliacao":
        logger.info(f"Running Conciliation process for {args.source_sheet}")
        app.run_conciliation_manual(source_sheet=args.source_sheet)
    elif args.command == "status":
        logger.info("Application ready")
        for line in app.status_lines():
            print(line)

    return 0


def main() -> int:
    """Program entrypoint for `python -m src.gmail_to_sheets.app`."""
    return run_cli()
