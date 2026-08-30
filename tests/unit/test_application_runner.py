from pathlib import Path
from unittest.mock import Mock, patch

from src.gmail_to_sheets.application_runner import AppRunner, build_parser, run_cli


def _make_settings() -> Mock:
    settings = Mock()
    settings.log_file = "logs/test.log"
    settings.log_level = "INFO"
    settings.batch_size = 10
    settings.attachment_extension = ".txt"
    settings.gmail = Mock()
    settings.gmail.search_query = "in:inbox has:attachment"
    settings.gmail.client_secrets_path = Path("/tmp/secret.json")
    settings.gmail.credentials_path = Path("/tmp/token.json")
    settings.gmail.backup_label_name = "Backup/Archive"
    settings.sheets = Mock()
    settings.sheets.service_account_path = Path("/tmp/service.json")
    settings.sheets.spreadsheet_id = "sheet-123"
    settings.sheets.sheet_name = "T_EXTRATO"
    return settings


class TestApplicationRunnerParser:
    def test_build_parser_includes_all_commands(self):
        parser = build_parser()
        for cmd in [
            "run-scheduled",
            "run-once",
            "extrato",
            "entradas",
            "dizimos-ofertas",
            "saidas",
            "conciliacao",
            "check-inbox",
            "status",
        ]:
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_build_parser_conciliacao_with_custom_sheet(self):
        parser = build_parser()
        args = parser.parse_args(["conciliacao", "CONTAORDEM"])
        assert args.command == "conciliacao"
        assert args.source_sheet == "CONTAORDEM"


class TestApplicationRunnerCLIRouting:
    @patch("src.gmail_to_sheets.application_runner.CentralOrchestrator")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch.object(AppRunner, "run_once")
    def test_run_cli_routes_run_once(
        self,
        mock_run_once,
        mock_load_settings,
        mock_setup_logging,
        mock_central_cls,
    ):
        settings = _make_settings()
        mock_load_settings.return_value = settings
        mock_central = Mock()
        mock_central.scheduler = Mock()
        mock_central.context = Mock()
        mock_central.status_lines.return_value = ["AppExtrato Orchestrator"]
        mock_central_cls.return_value = mock_central

        exit_code = run_cli(["run-once"])

        assert exit_code == 0
        mock_run_once.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.CentralOrchestrator")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch.object(AppRunner, "run_interactive")
    def test_run_cli_routes_run_scheduled(
        self,
        mock_run_interactive,
        mock_load_settings,
        mock_setup_logging,
        mock_central_cls,
    ):
        settings = _make_settings()
        mock_load_settings.return_value = settings
        mock_central = Mock()
        mock_central.scheduler = Mock()
        mock_central.context = Mock()
        mock_central.status_lines.return_value = ["AppExtrato Orchestrator"]
        mock_central_cls.return_value = mock_central

        exit_code = run_cli(["run-scheduled"])

        assert exit_code == 0
        mock_run_interactive.assert_called_once()


    @patch("src.gmail_to_sheets.application_runner.CentralOrchestrator")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch.object(AppRunner, "run_entradas_once")
    def test_run_cli_routes_dizimos_ofertas(
        self,
        mock_run,
        mock_load_settings,
        mock_setup_logging,
        mock_central_cls,
    ):
        settings = _make_settings()
        mock_load_settings.return_value = settings
        mock_central = Mock()
        mock_central.scheduler = Mock()
        mock_central.context = Mock()
        mock_central_cls.return_value = mock_central

        exit_code = run_cli(["dizimos-ofertas"])

        assert exit_code == 0
        mock_run.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.CentralOrchestrator")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch.object(AppRunner, "run_saidas_once")
    def test_run_cli_routes_saidas(
        self,
        mock_run,
        mock_load_settings,
        mock_setup_logging,
        mock_central_cls,
    ):
        settings = _make_settings()
        mock_load_settings.return_value = settings
        mock_central = Mock()
        mock_central.scheduler = Mock()
        mock_central.context = Mock()
        mock_central_cls.return_value = mock_central

        exit_code = run_cli(["saidas"])

        assert exit_code == 0
        mock_run.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.CentralOrchestrator")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch.object(AppRunner, "status_lines")
    def test_run_cli_routes_status(
        self,
        mock_status_lines,
        mock_load_settings,
        mock_setup_logging,
        mock_central_cls,
        capsys,
    ):
        settings = _make_settings()
        mock_load_settings.return_value = settings
        mock_central = Mock()
        mock_central.scheduler = Mock()
        mock_central.context = Mock()
        mock_central.status_lines.return_value = [
            "AppExtrato Orchestrator",
            "Scheduler interval: 60 seconds",
            "Processes:",
            "  Extrato      priority=10",
            "  DizimosOfertas priority=20",
            "  Saidas       priority=30",
            "  Conciliacao  priority=40",
        ]
        mock_central_cls.return_value = mock_central
        mock_status_lines.return_value = mock_central.status_lines.return_value

        exit_code = run_cli(["status"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "AppExtrato Orchestrator" in captured.out
        assert "Scheduler interval: 60 seconds" in captured.out
