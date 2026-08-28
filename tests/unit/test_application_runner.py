from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from src.gmail_to_sheets.application_runner import AppRunner, build_parser, run_cli


class TestApplicationRunnerParser:
    def test_build_parser_includes_all_commands(self):
        parser = build_parser()
        for cmd in ["run-scheduled", "run-once", "extrato", "entradas", "conciliacao", "check-inbox", "status"]:
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_build_parser_conciliacao_with_custom_sheet(self):
        parser = build_parser()
        args = parser.parse_args(["conciliacao", "CONTAORDEM"])
        assert args.command == "conciliacao"
        assert args.source_sheet == "CONTAORDEM"


class TestApplicationRunnerProcessExecution:
    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.ExtratoOrchestrator")
    def test_run_extrato_executes_orchestrator(
        self,
        mock_extrato_orchestrator_cls,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        mock_orch = Mock()
        mock_extrato_orchestrator_cls.return_value = mock_orch

        app = AppRunner()
        app.run_extrato()

        mock_extrato_orchestrator_cls.assert_called_once()
        mock_orch.run.assert_called_once()
        assert app.extrato_running is False

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.EntradasOrchestrator")
    def test_run_entradas_executes_orchestrator(
        self,
        mock_entradas_orchestrator_cls,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        mock_orch = Mock()
        mock_entradas_orchestrator_cls.return_value = mock_orch

        app = AppRunner()
        app.run_entradas()

        mock_entradas_orchestrator_cls.assert_called_once()
        mock_orch.run.assert_called_once()
        assert app.entradas_running is False

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.ConciliationOrchestrator")
    def test_run_conciliation_executes_orchestrator(
        self,
        mock_conciliation_orchestrator_cls,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        mock_orch = Mock()
        mock_conciliation_orchestrator_cls.return_value = mock_orch

        app = AppRunner()
        app.run_conciliation(source_sheet="T_EXTRATO")

        mock_conciliation_orchestrator_cls.assert_called_once_with(source_sheet="T_EXTRATO")
        mock_orch.run.assert_called_once()
        assert app.conciliacao_running is False

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    def test_run_full_cycle_executes_in_order(
        self,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        app = AppRunner()
        app.run_extrato = Mock()
        app.run_entradas = Mock()
        app.run_conciliation = Mock()

        app.run_full_cycle()

        app.run_extrato.assert_called_once()
        app.run_entradas.assert_called_once()
        app.run_conciliation.assert_called_once_with(source_sheet="T_EXTRATO")

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    def test_start_scheduler_registers_full_cycle(
        self,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        mock_scheduler = Mock()
        mock_scheduler_cls.return_value = mock_scheduler

        app = AppRunner()
        app.start_scheduler()

        assert app.is_running is True
        mock_scheduler.add_job.assert_called_once()
        job_kwargs = mock_scheduler.add_job.call_args[1]
        assert job_kwargs["id"] == "full_cycle_job"
        mock_scheduler.start.assert_called_once()


class TestApplicationRunnerInboxValidation:
    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.GmailClient")
    @patch("src.gmail_to_sheets.application_runner.GmailAuthenticator")
    def test_check_inbox_is_read_only(
        self,
        mock_authenticator_cls,
        mock_gmail_client_cls,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        settings = Mock()
        settings.log_file = "logs/test.log"
        settings.log_level = "INFO"
        settings.batch_size = 10
        settings.attachment_extension = ".txt"
        settings.gmail = Mock()
        settings.gmail.search_query = "in:inbox has:attachment"
        settings.gmail.client_secrets_path = Path("/tmp/secret.json")
        settings.gmail.credentials_path = Path("/tmp/token.json")
        mock_load_settings.return_value = settings
        mock_scheduler_cls.return_value = Mock()

        mock_authenticator = Mock()
        mock_authenticator.get_credentials.return_value = Mock()
        mock_authenticator_cls.return_value = mock_authenticator

        fake_client = Mock()
        fake_client.search_messages.return_value = ["msg-1"]
        fake_client.get_message.return_value = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "MT940 file"},
                    {"name": "From", "value": "noreply@example.com"},
                    {"name": "Date", "value": "Thu, 27 Aug 2026 10:00:00 +0100"},
                ]
            }
        }
        fake_client.get_attachments.return_value = [
            {"filename": "statement.txt", "attachment_id": "att-1", "mime_type": "text/plain", "part_id": "1"}
        ]
        mock_gmail_client_cls.return_value = fake_client

        app = AppRunner()
        summaries = app.check_inbox()

        assert len(summaries) == 1
        assert summaries[0]["message_id"] == "msg-1"
        assert summaries[0]["attachment_count"] == 1
        fake_client.search_messages.assert_called_once_with(
            query="in:inbox has:attachment",
            max_results=10,
        )
        fake_client.get_message.assert_called_once_with("msg-1")
        fake_client.get_attachments.assert_called_once_with(
            "msg-1",
            attachment_extension=".txt",
        )
        assert mock_gmail_client_cls.call_count == 1


class TestApplicationRunnerCLIRouting:
    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.AppRunner.run_once")
    def test_run_cli_routes_run_once(
        self,
        mock_run_once,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        exit_code = run_cli(["run-once"])
        assert exit_code == 0
        mock_run_once.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.AppRunner.run_extrato_once")
    def test_run_cli_routes_extrato(
        self,
        mock_run_extrato_once,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        exit_code = run_cli(["extrato"])
        assert exit_code == 0
        mock_run_extrato_once.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.AppRunner.run_entradas_once")
    def test_run_cli_routes_entradas(
        self,
        mock_run_entradas_once,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        exit_code = run_cli(["entradas"])
        assert exit_code == 0
        mock_run_entradas_once.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.AppRunner.run_conciliation_manual")
    def test_run_cli_routes_conciliacao(
        self,
        mock_run_conciliation,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        exit_code = run_cli(["conciliacao", "T_EXTRATO"])
        assert exit_code == 0
        mock_run_conciliation.assert_called_once_with(source_sheet="T_EXTRATO")

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    @patch("src.gmail_to_sheets.application_runner.AppRunner.check_inbox")
    def test_run_cli_routes_check_inbox(
        self,
        mock_check_inbox,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        exit_code = run_cli(["check-inbox"])
        assert exit_code == 0
        mock_check_inbox.assert_called_once()

    @patch("src.gmail_to_sheets.application_runner.BackgroundScheduler")
    @patch("src.gmail_to_sheets.application_runner.setup_logging")
    @patch("src.gmail_to_sheets.application_runner.load_settings")
    def test_run_cli_routes_status(
        self,
        mock_load_settings,
        mock_setup_logging,
        mock_scheduler_cls,
    ):
        exit_code = run_cli(["status"])
        assert exit_code == 0
