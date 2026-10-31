from pathlib import Path

import pytest

from src.gmail_to_sheets.processes.financial_duplicate_audit import cli
from src.gmail_to_sheets.processes.financial_duplicate_audit.models import AuditRun


def test_cli_requires_dry_run_and_rejects_apply() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--ano", "2026", "--mes", "10"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--ano", "2026", "--mes", "10", "--apply"])


@pytest.mark.parametrize("month", [0, 13])
def test_cli_rejects_invalid_month(month: int) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--ano", "2026", "--mes", str(month), "--dry-run"])


def test_run_cli_executes_read_only_runner_and_writes_period_reports(tmp_path, monkeypatch) -> None:
    calls: list[tuple[int, int]] = []

    class Settings:
        class sheets:
            service_account_path = Path("credentials.json")
            spreadsheet_id = "main"

        class verbo_cafe:
            source_spreadsheet_id = "verbo"

    class Runner:
        def __init__(self, client, spreadsheet_id, **kwargs):
            assert spreadsheet_id == "main"
            assert kwargs["verbo_cafe_spreadsheet_id"] == "verbo"

        def run(self, *, year: int, month: int):
            calls.append((year, month))
            return AuditRun(year, month, 0, 0, (), ())

    monkeypatch.chdir(tmp_path)
    exit_code = cli.run_cli(
        ["--ano", "2026", "--mes", "10", "--dry-run"],
        settings_loader=lambda: Settings(),
        client_factory=lambda path: object(),
        runner_factory=Runner,
    )

    assert exit_code == 0
    assert calls == [(2026, 10)]
    assert (tmp_path / "logs/financial_duplicate_audit/2026-10/audit.json").exists()
