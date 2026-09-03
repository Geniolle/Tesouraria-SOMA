from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from src.gmail_to_sheets.config.settings import FaturasEmailRoute
from src.gmail_to_sheets.orchestration.models import ProcessContext
from src.gmail_to_sheets.orchestration.processes import FaturasEmailProcess
from src.gmail_to_sheets.processes.faturas_email.filename import (
    build_drive_filename,
    next_available_name,
)
from src.gmail_to_sheets.processes.faturas_email.orchestrator import (
    FaturasEmailOrchestrator,
)

LISBON = ZoneInfo("Europe/Lisbon")


def _route(**over):
    base = {
        "sender": "elpemi.investimentos@gmail.com",
        "drive_folder_id": "FOLDER",
        "label": "Aluguer São Vicente/Facturas",
        "filename_token": "Aluguel",
    }
    base.update(over)
    return FaturasEmailRoute(**base)


def _settings(routes, ext=".pdf"):
    return SimpleNamespace(
        timezone="Europe/Lisbon",
        batch_size=50,
        faturas_email=SimpleNamespace(routes=routes, attachment_ext=ext),
    )


def _internal_date(dt):
    return str(int(dt.timestamp() * 1000))


def _message(dt, parts):
    return {"internalDate": _internal_date(dt), "payload": {"parts": parts}}


_PDF_PART = {
    "filename": "fatura.pdf",
    "mimeType": "application/pdf",
    "body": {"attachmentId": "att-1"},
}


class TestFilename:
    def test_build_drive_filename(self):
        name = build_drive_filename(
            datetime(2026, 2, 15, tzinfo=LISBON), "Aluguel", "Fatura Jan.pdf"
        )
        assert name == "2026_02_15_Aluguel_Fatura Jan.pdf"

    def test_build_drive_filename_sanitizes_slash(self):
        name = build_drive_filename(
            datetime(2026, 2, 15, tzinfo=LISBON), "Aluguel", "a/b:c.pdf"
        )
        assert name == "2026_02_15_Aluguel_a_b_c.pdf"

    def test_next_available_name(self):
        assert next_available_name("x.pdf", set()) == "x.pdf"
        assert next_available_name("x.pdf", {"x.pdf"}) == "x (1).pdf"
        assert (
            next_available_name("x.pdf", {"x.pdf", "x (1).pdf"}) == "x (2).pdf"
        )


class TestCollectAttachments:
    def test_walks_nested_tree_and_filters_extension(self):
        payload = {
            "parts": [
                {"mimeType": "text/plain", "body": {}},
                {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        _PDF_PART,
                        {
                            "filename": "logo.png",
                            "body": {"attachmentId": "att-2"},
                        },
                    ],
                },
            ]
        }
        found = FaturasEmailOrchestrator._collect_attachments(payload, ".pdf")
        assert [a["filename"] for a in found] == ["fatura.pdf"]
        assert found[0]["attachment_id"] == "att-1"


class TestFaturasEmailOrchestrator:
    def _gmail(self, message):
        gmail = Mock()
        gmail.search_messages.return_value = ["m1"]
        gmail.get_message.return_value = message
        gmail.download_attachment.return_value = b"PDFDATA"
        return gmail

    def _drive(self, existing=None):
        drive = Mock()
        drive.list_child_names.return_value = set(existing or [])
        drive.upload_bytes.side_effect = lambda name, *a, **k: {
            "id": "f1",
            "name": name,
        }
        return drive

    def test_uploads_then_labels_and_archives(self):
        msg = _message(datetime(2026, 2, 15, 10, tzinfo=LISBON), [_PDF_PART])
        gmail = self._gmail(msg)
        drive = self._drive()
        orch = FaturasEmailOrchestrator(
            settings=_settings([_route()]),
            gmail_client=gmail,
            drive_client=drive,
        )

        summary = orch.run()

        drive.upload_bytes.assert_called_once()
        name = drive.upload_bytes.call_args.args[0]
        assert name == "2026_02_15_Aluguel_fatura.pdf"
        gmail.add_label.assert_called_once_with(
            "m1", "Aluguer São Vicente/Facturas"
        )
        gmail.archive_message.assert_called_once_with("m1")
        assert summary == {
            "processed": 1,
            "uploaded": 1,
            "renamed": 0,
            "skipped_no_attachment": 0,
            "errors": 0,
        }

    def test_name_clash_gets_suffix(self):
        msg = _message(datetime(2026, 2, 15, 10, tzinfo=LISBON), [_PDF_PART])
        drive = self._drive(existing=["2026_02_15_Aluguel_fatura.pdf"])
        orch = FaturasEmailOrchestrator(
            settings=_settings([_route()]),
            gmail_client=self._gmail(msg),
            drive_client=drive,
        )

        summary = orch.run()

        assert (
            drive.upload_bytes.call_args.args[0]
            == "2026_02_15_Aluguel_fatura (1).pdf"
        )
        assert summary["renamed"] == 1

    def test_no_matching_attachment_still_labels_and_archives(self):
        part = {"filename": "nota.txt", "body": {"attachmentId": "x"}}
        msg = _message(datetime(2026, 2, 15, 10, tzinfo=LISBON), [part])
        gmail = self._gmail(msg)
        drive = self._drive()
        orch = FaturasEmailOrchestrator(
            settings=_settings([_route()]),
            gmail_client=gmail,
            drive_client=drive,
        )

        summary = orch.run()

        drive.upload_bytes.assert_not_called()
        gmail.add_label.assert_called_once()
        gmail.archive_message.assert_called_once_with("m1")
        assert summary["skipped_no_attachment"] == 1
        assert summary["processed"] == 1

    def test_no_routes_is_a_noop(self):
        gmail = Mock()
        orch = FaturasEmailOrchestrator(
            settings=_settings([]),
            gmail_client=gmail,
            drive_client=Mock(),
        )

        summary = orch.run()

        gmail.search_messages.assert_not_called()
        assert summary["processed"] == 0


class TestFaturasEmailProcessPending:
    def _context(self, routes, matches):
        gmail = Mock()
        gmail.search_messages.side_effect = (
            lambda query, max_results: ["m1"] if matches else []
        )
        settings = _settings(routes)
        return ProcessContext(settings=settings, gmail_client=gmail), gmail

    def test_pending_true_when_a_route_matches(self):
        context, gmail = self._context([_route()], matches=True)
        result = FaturasEmailProcess(context).check_pending()
        assert result.has_work is True
        gmail.search_messages.assert_called_once_with(
            query="in:inbox from:elpemi.investimentos@gmail.com",
            max_results=1,
        )

    def test_pending_false_when_no_match(self):
        context, _ = self._context([_route()], matches=False)
        assert FaturasEmailProcess(context).check_pending().has_work is False

    def test_pending_false_when_no_routes(self):
        context, gmail = self._context([], matches=True)
        assert FaturasEmailProcess(context).check_pending().has_work is False
        gmail.search_messages.assert_not_called()
