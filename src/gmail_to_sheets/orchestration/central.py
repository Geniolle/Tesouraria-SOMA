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

from .health import (
    HealthStore,
    ProcessHealth,
    ProcessHealthState,
    utc_now_iso,
)
from .models import ProcessContext, ProcessResult, ProcessStatus
from .processes import (
    ConciliacaoProcess,
    DizimosOfertasProcess,
    ExtratoProcess,
    SaidasProcess,
)
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
    failure_alert_threshold = 3

    def __init__(
        self,
        settings=None,
        registry: ProcessRegistry | None = None,
        health_store: HealthStore | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        setup_logging(self.settings.log_file, self.settings.log_level)
        self.context = ProcessContext(settings=self.settings)
        self.registry = registry or ProcessRegistry(
            [
                ExtratoProcess(self.context),
                DizimosOfertasProcess(self.context),
                SaidasProcess(self.context),
                ConciliacaoProcess(self.context),
            ]
        )
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.health_store = health_store or HealthStore()
        self.health = self.health_store.load()
        for process in self.registry:
            self.health.setdefault(
                process.name,
                ProcessHealth(process_name=process.name),
            )

    def _health_for(self, process_name: str) -> ProcessHealth:
        return self.health.setdefault(
            process_name,
            ProcessHealth(process_name=process_name),
        )

    def _persist_health(self) -> None:
        try:
            self.health_store.save(self.health)
        except Exception:
            logger.exception("Unable to persist orchestrator health state")

    def _mark_idle(self, process_name: str, pending_count: int) -> None:
        health = self._health_for(process_name)
        health.state = ProcessHealthState.IDLE
        health.last_pending_count = pending_count
        health.consecutive_failures = 0
        health.last_error = None
        self._persist_health()

    def _mark_success(
        self,
        process_name: str,
        result: ProcessResult,
    ) -> None:
        health = self._health_for(process_name)
        health.state = ProcessHealthState.SUCCESS
        health.last_success_at = utc_now_iso()
        health.last_duration_seconds = result.duration_seconds
        health.consecutive_failures = 0
        health.last_error = None
        self._persist_health()

    def _mark_failure(
        self,
        process_name: str,
        error: str,
        *,
        duration_seconds: float,
    ) -> None:
        health = self._health_for(process_name)
        health.state = ProcessHealthState.FAILED
        health.last_failure_at = utc_now_iso()
        health.last_duration_seconds = duration_seconds
        health.last_error = error[:1000]
        health.consecutive_failures += 1
        self._persist_health()
        self._maybe_alert(process_name, health)

    def _maybe_alert(
        self,
        process_name: str,
        health: ProcessHealth,
    ) -> None:
        failures = health.consecutive_failures
        if failures < self.failure_alert_threshold:
            return

        if failures == self.failure_alert_threshold or failures % 10 == 0:
            logger.critical(
                "PROCESS HEALTH ALERT process=%s consecutive_failures=%s "
                "last_error=%s",
                process_name,
                failures,
                health.last_error or "unknown",
            )

    def run_tick(self) -> TickSummary:
        """Run one sequential orchestration tick."""
        started_at = perf_counter()
        logger.info("ORCHESTRATOR TICK START")

        results: list[ProcessResult] = []

        for process in self.registry:
            health = self._health_for(process.name)
            health.last_check_at = utc_now_iso()
            check_started_at = perf_counter()

            try:
                pending = process.check_pending()
                health.last_pending_count = pending.count
            except KeyboardInterrupt:
                raise
            except Exception as error:
                duration = perf_counter() - check_started_at
                logger.exception("%s pending check failed", process.name)
                result = ProcessResult(
                    process_name=process.name,
                    status=ProcessStatus.FAILED,
                    processed=0,
                    duration_seconds=duration,
                    error=str(error),
                )
                results.append(result)
                self._mark_failure(
                    process.name,
                    str(error),
                    duration_seconds=duration,
                )
                continue

            if not pending.has_work:
                result = ProcessResult(
                    process_name=process.name,
                    status=ProcessStatus.SKIPPED,
                    processed=0,
                    duration_seconds=perf_counter() - check_started_at,
                    error=pending.reason or None,
                )
                logger.info(
                    "%-12s SKIPPED pending=%s",
                    process.name,
                    pending.count,
                )
                results.append(result)
                self._mark_idle(process.name, pending.count)
                continue

            logger.info(
                "%-12s PENDING count=%s",
                process.name,
                pending.count,
            )
            health.last_run_at = utc_now_iso()
            run_started_at = perf_counter()

            try:
                result = process.run()
                results.append(result)
            except KeyboardInterrupt:
                raise
            except Exception as error:
                duration = perf_counter() - run_started_at
                logger.exception("%s failed during tick", process.name)
                result = ProcessResult(
                    process_name=process.name,
                    status=ProcessStatus.FAILED,
                    processed=0,
                    duration_seconds=duration,
                    error=str(error),
                )
                results.append(result)

            if result.status == ProcessStatus.SUCCESS:
                logger.info(
                    "%-12s SUCCESS processed=%s",
                    process.name,
                    result.processed,
                )
                self._mark_success(process.name, result)
            elif result.status == ProcessStatus.SKIPPED:
                logger.info(
                    "%-12s SKIPPED pending=%s",
                    process.name,
                    pending.count,
                )
                self._mark_idle(process.name, pending.count)
            else:
                error = result.error or "unknown"
                logger.error(
                    "%-12s FAILED error=%s",
                    process.name,
                    error,
                )
                duration = result.duration_seconds or (
                    perf_counter() - run_started_at
                )
                self._mark_failure(
                    process.name,
                    error,
                    duration_seconds=duration,
                )

        duration = perf_counter() - started_at
        logger.info("ORCHESTRATOR TICK END duration=%.2fs", duration)
        return TickSummary(
            results=results,
            duration_seconds=duration,
        )

    def start_scheduler(self) -> None:
        """Start the single scheduler job."""
        logger.info("Starting central orchestrator scheduler...")
        self.scheduler.add_job(
            self.run_tick,
            trigger=IntervalTrigger(
                seconds=self.scheduler_interval_seconds
            ),
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
        logger.info(
            "  Processes:  %s",
            " -> ".join(process.name for process in self.registry),
        )
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
        """Return local health status without contacting external services."""
        persisted = self.health_store.load()
        lines = [
            "AppExtrato Orchestrator",
            f"Scheduler interval: {self.scheduler_interval_seconds} seconds",
            "Processes:",
        ]

        for process in self.registry:
            health = persisted.get(process.name) or self._health_for(
                process.name
            )
            last_run = health.last_run_at or "-"
            last_success = health.last_success_at or "-"
            lines.append(
                f"  {process.name:<12} priority={process.priority:<2} "
                f"state={health.state.value:<7} "
                f"failures={health.consecutive_failures:<3} "
                f"last_run={last_run} "
                f"last_success={last_success}"
            )

        return lines
