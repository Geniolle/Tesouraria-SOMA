"""Tests for the accountant-folder listing used by the dashboard."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard"))

import accountant  # noqa: E402


def test_list_names_follows_pages() -> None:
    files = MagicMock()
    files.list.return_value.execute.side_effect = [
        {"files": [{"name": "a.pdf"}], "nextPageToken": "t"},
        {"files": [{"name": "b.pdf"}]},
    ]
    with patch.object(accountant, "build") as build:
        build.return_value.files.return_value = files
        assert accountant.list_names(object(), "folder") == ["a.pdf", "b.pdf"]
    assert files.list.call_args_list[1].kwargs["pageToken"] == "t"


def test_from_year_keeps_only_dated_names_from_that_year() -> None:
    names = ["20251231_x.jpg", "20260105_y.jpg", "2026_02_04_EDP.pdf", "Repasse MVV 01-26.pdf"]
    assert accountant.from_year(names, "2026") == ["20260105_y.jpg", "2026_02_04_EDP.pdf"]
    assert accountant.from_year(names, None) == names
