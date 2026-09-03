from unittest.mock import Mock

from src.gmail_to_sheets.clients.drive_client import DriveClient


def _client_with_service(service):
    client = DriveClient.__new__(DriveClient)
    client.service = service
    client.credentials = Mock()
    return client


class TestListChildNames:
    def test_paginates_and_returns_name_set(self):
        service = Mock()
        pages = [
            {"files": [{"name": "a.pdf"}, {"name": "b.pdf"}],
             "nextPageToken": "p2"},
            {"files": [{"name": "c.pdf"}]},
        ]
        service.files.return_value.list.return_value.execute.side_effect = pages

        names = _client_with_service(service).list_child_names("FOLDER")

        assert names == {"a.pdf", "b.pdf", "c.pdf"}
        assert service.files.return_value.list.call_count == 2


class TestUploadBytes:
    def test_creates_file_in_folder(self):
        service = Mock()
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "f1",
            "name": "doc.pdf",
            "webViewLink": "http://x",
        }

        result = _client_with_service(service).upload_bytes(
            "doc.pdf", b"DATA", "application/pdf", "FOLDER"
        )

        assert result["id"] == "f1"
        kwargs = service.files.return_value.create.call_args.kwargs
        assert kwargs["body"] == {"name": "doc.pdf", "parents": ["FOLDER"]}
        assert kwargs["supportsAllDrives"] is True
