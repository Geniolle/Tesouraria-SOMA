from dataclasses import dataclass
from unittest.mock import Mock, patch

from src.gmail_to_sheets.orchestration.central import CentralOrchestrator
from src.gmail_to_sheets.orchestration.models import PendingResult, ProcessResult, ProcessStatus
from src.gmail_to_sheets.orchestration.registry import ProcessRegistry


def _make_settings() -> Mock:
    settings = Mock()
    settings.log_file = "logs/test.log"
    settings.log_level = "INFO"
    settings.gmail = Mock()
    settings.gmail.client_secrets_path = "/tmp/secret.json"
    settings.gmail.credentials_path = "/tmp/token.json"
    settings.gmail.search_query = "in:inbox has:attachment"
    settings.sheets = Mock()
    settings.sheets.service_account_path = "/tmp/service.json"
    settings.sheets.spreadsheet_id = "sheet-123"
    settings.sheets.sheet_name = "T_EXTRATO"
    return settings


@dataclass
class FakeProcess:
    name: str
    priority: int
    pending: PendingResult
    result: ProcessResult | None = None
    run_side_effect: Exception | None = None
    check_pending_calls: int = 0
    run_calls: int = 0

    def check_pending(self) -> PendingResult:
        self.check_pending_calls += 1
        return self.pending

    def run(self) -> ProcessResult:
        self.run_calls += 1
        if self.run_side_effect:
            raise self.run_side_effect
        return self.result or ProcessResult(
            process_name=self.name,
            status=ProcessStatus.SUCCESS,
            processed=1,
            duration_seconds=0.0,
        )


class TestProcessRegistry:
    def test_registry_orders_by_priority(self):
        registry = ProcessRegistry(
            [
                FakeProcess("Conciliacao", 30, PendingResult(False)),
                FakeProcess("Extrato", 10, PendingResult(False)),
                FakeProcess("Entradas", 20, PendingResult(False)),
            ]
        )

        assert [process.name for process in registry.list()] == [
            "Extrato",
            "Entradas",
            "Conciliacao",
        ]


class TestCentralOrchestratorScheduler:
    @patch("src.gmail_to_sheets.orchestration.central.BackgroundScheduler")
    @patch("src.gmail_to_sheets.orchestration.central.IntervalTrigger")
    @patch("src.gmail_to_sheets.orchestration.central.setup_logging")
    def test_scheduler_configured_for_sixty_seconds(
        self,
        mock_setup_logging,
        mock_interval_trigger,
        mock_scheduler_cls,
    ):
        settings = _make_settings()
        mock_scheduler = Mock()
        mock_scheduler_cls.return_value = mock_scheduler

        orchestrator = CentralOrchestrator(settings=settings, registry=ProcessRegistry())
        orchestrator.start_scheduler()

        mock_interval_trigger.assert_called_once_with(seconds=60)
        mock_scheduler.add_job.assert_called_once()
        job_kwargs = mock_scheduler.add_job.call_args.kwargs
        assert job_kwargs["max_instances"] == 1
        assert job_kwargs["coalesce"] is True
        assert job_kwargs["misfire_grace_time"] == 60
        assert orchestrator.is_running is True


class TestCentralOrchestratorTick:
    @patch("src.gmail_to_sheets.orchestration.central.setup_logging")
    def test_tick_skips_process_without_pending(self, mock_setup_logging):
        settings = _make_settings()
        process = FakeProcess(
            name="Extrato",
            priority=10,
            pending=PendingResult(has_work=False, count=0, reason="none"),
        )
        orchestrator = CentralOrchestrator(
            settings=settings,
            registry=ProcessRegistry([process]),
        )

        summary = orchestrator.run_tick()

        assert process.check_pending_calls == 1
        assert process.run_calls == 0
        assert summary.results[0].status == ProcessStatus.SKIPPED

    @patch("src.gmail_to_sheets.orchestration.central.setup_logging")
    def test_tick_runs_process_with_pending_once(self, mock_setup_logging):
        settings = _make_settings()
        process = FakeProcess(
            name="Extrato",
            priority=10,
            pending=PendingResult(has_work=True, count=1, reason="work"),
            result=ProcessResult(
                process_name="Extrato",
                status=ProcessStatus.SUCCESS,
                processed=2,
                duration_seconds=0.1,
            ),
        )
        orchestrator = CentralOrchestrator(
            settings=settings,
            registry=ProcessRegistry([process]),
        )

        summary = orchestrator.run_tick()

        assert process.check_pending_calls == 1
        assert process.run_calls == 1
        assert summary.results[0].status == ProcessStatus.SUCCESS
        assert summary.results[0].processed == 2

    @patch("src.gmail_to_sheets.orchestration.central.setup_logging")
    def test_tick_continues_after_failure(self, mock_setup_logging):
        settings = _make_settings()
        failing = FakeProcess(
            name="Extrato",
            priority=10,
            pending=PendingResult(has_work=True, count=1, reason="work"),
            run_side_effect=RuntimeError("boom"),
        )
        succeeding = FakeProcess(
            name="Entradas",
            priority=20,
            pending=PendingResult(has_work=True, count=1, reason="work"),
            result=ProcessResult(
                process_name="Entradas",
                status=ProcessStatus.SUCCESS,
                processed=1,
                duration_seconds=0.1,
            ),
        )
        orchestrator = CentralOrchestrator(
            settings=settings,
            registry=ProcessRegistry([failing, succeeding]),
        )

        summary = orchestrator.run_tick()

        assert failing.run_calls == 1
        assert succeeding.run_calls == 1
        assert [result.status for result in summary.results] == [
            ProcessStatus.FAILED,
            ProcessStatus.SUCCESS,
        ]

    @patch("src.gmail_to_sheets.orchestration.central.setup_logging")
    def test_tick_summary_contains_duration_and_results(self, mock_setup_logging):
        settings = _make_settings()
        process = FakeProcess(
            name="Conciliacao",
            priority=30,
            pending=PendingResult(has_work=False, count=0, reason="none"),
        )
        orchestrator = CentralOrchestrator(
            settings=settings,
            registry=ProcessRegistry([process]),
        )

        summary = orchestrator.run_tick()

        assert summary.duration_seconds >= 0
        assert len(summary.results) == 1

