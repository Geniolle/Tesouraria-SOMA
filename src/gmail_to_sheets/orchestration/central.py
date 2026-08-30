"""Central orchestration tick and scheduler."""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from time import perf_counter

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.gmail_to_sheets.config.settings import load_settings
from src.gmail_to_sheets.logging_config import setup_logging

from .models import ProcessContext, ProcessResult, ProcessStatus
from .processes import ConciliacaoProcess, EntradasProcess, ExtratoProcess
from .registry import ProcessRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TickSummary:
    """Compact summary for a single orchestration tick."""

    results: list[ProcessResult]
    duration_seconds: float


class CentralOrchestrator:
    """Single scheduler entrypoint for all managed processes."""

    scheduler_interval_seconds = 60

    def __init__(self, settings=None, registry: ProcessRegistry | None = None) -> None:
        self.settings = settings or load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.context = ProcessContext(settings=self.settings)
        self.registry = registry or ProcessRegistry(
            [
                ExtratoProcess(self.context),
                EntradasProcess(self.context),
                ConciliacaoProcess(self.context),
            ]
        )
        self.scheduler = BackgroundScheduler()
        self.is_running = False

    def run_tick(self) -> TickSummary:
        """Run one sequential orchestration tick."""
        started_at = perf_counter()
        logger.info("ORCHESTRATOR TICK START")

        results: list[ProcessResult] = []
        for process in self.registry:
            try:
                pending = process.check_pending()
            except KeyboardInterrupt:
                raise
            except Exception as error:
                logger.exception("%s pending check failed", process.name)
                results.append(
                    ProcessResult(
                        process_name=process.name,
                        status=ProcessStatus.FAILED,
                        processed=0,
                        duration_seconds=0.0,
                        error=str(error),
                    )
                )
                continue

            if not pending.has_work:
                result = ProcessResult(
                    process_name=process.name,
                    status=ProcessStatus.SKIPPED,
                    processed=0,
                    duration_seconds=0.0,
                    error=pending.reason or None,
                )
                logger.info("%-12s SKIPPED pending=%s", process.name, pending.count)
                results.append(result)
                continue

            logger.info("%-12s PENDING count=%s", process.name, pending.count)
            try:
                result = process.run()
                results.append(result)
                if result.status == ProcessStatus.SUCCESS:
                    logger.info("%-12s SUCCESS processed=%s", process.name, result.processed)
                elif result.status == ProcessStatus.SKIPPED:
                    logger.info("%-12s SKIPPED pending=%s", process.name, pending.count)
                else:
                    logger.info("%-12s FAILED error=%s", process.name, result.error or "unknown")
            except KeyboardInterrupt:
                raise
            except Exception as error:
                logger.exception("%s failed during tick", process.name)
                results.append(
                    ProcessResult(
                        process_name=process.name,
                        status=ProcessStatus.FAILED,
                        processed=0,
                        duration_seconds=0.0,
                        error=str(error),
                    )
                )

        duration = perf_counter() - started_at
        logger.info("ORCHESTRATOR TICK END duration=%.2fs", duration)
        return TickSummary(results=results, duration_seconds=duration)

    def start_scheduler(self) -> None:
        """Start the single scheduler job."""
        logger.info("Starting central orchestrator scheduler...")
        self.scheduler.add_job(
            self.run_tick,
            trigger=IntervalTrigger(seconds=self.scheduler_interval_seconds),
            id="orchestrator_tick",
            name="Central orchestration tick (every 60 seconds)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        self.scheduler.start()
        self.is_running = True
        logger.info("Scheduler started successfully")
        logger.info("=" * 80)
        logger.info("SCHEDULE:")
        logger.info("  Tick:       every 60 seconds")
        logger.info("  Processes:  Extrato -> Entradas -> Conciliacao")
        logger.info("=" * 80)

    def stop_scheduler(self) -> None:
        """Stop the scheduler gracefully."""
        if self.is_running and self.scheduler.running:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Scheduler stopped successfully")

    def run_interactive(self) -> None:
        """Run the scheduler until interrupted."""

        def signal_handler(signum, frame):
            logger.info("Received signal %s", signum)
            self.stop_scheduler()
            raise SystemExit(0)

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
            raise SystemExit(0)
        except Exception:
            logger.exception("Application error")
            self.stop_scheduler()
            raise

    def status_lines(self) -> list[str]:
        """Return static status output without contacting external services."""
        lines = [
            "AppExtrato Orchestrator",
            f"Scheduler interval: {self.scheduler_interval_seconds} seconds",
            "Processes:",
        ]
        for process in self.registry:
            lines.append(f"  {process.name:<12} priority={process.priority}")
        return lines
