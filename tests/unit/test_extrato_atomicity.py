from __future__ import annotations

import pytest

from src.gmail_to_sheets.processes.extrato.transfer_matching_layout import TransferMatchingLayout
from src.gmail_to_sheets.processes.extrato.transfer_service_support import parse_amount
from src.gmail_to_sheets.services.batch_writer import BatchWriter


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.180,00", 1180.0),
        ("1180,00", 1180.0),
        ("1.180,50", 1180.5),
        ("1180.50", 1180.5),
        ("-1.180,00", -1180.0),
    ],
)
def test_parse_amount_accepts_portuguese_thousands(raw, expected):
    assert parse_amount(raw) == expected
    assert TransferMatchingLayout.parse_amount(raw) == expected


def test_parse_amount_rejects_invalid_non_empty_value():
    with pytest.raises(ValueError):
        parse_amount("valor-invalido")

    with pytest.raises(ValueError):
        TransferMatchingLayout.parse_amount("valor-invalido")


class _QuotaClient:
    def __init__(self):
        self.append_attempts = 0

    def append_rows(self, spreadsheet_id, target_sheet, target_data):
        self.append_attempts += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")


def test_quota_failure_never_updates_source_status(monkeypatch):
    client = _QuotaClient()
    writer = BatchWriter(client, "sheet-id")

    sleeps = []
    monkeypatch.setattr(
        "src.gmail_to_sheets.services.batch_writer.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    status_calls = []
    monkeypatch.setattr(
        writer,
        "_batch_update_status",
        lambda *args, **kwargs: status_calls.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="429"):
        writer.batch_write_with_updates(
            source_sheet="T_EXTRATO",
            source_data=[],
            target_sheet="CONTAORDEM",
            target_data=[["05/10/2026", "", "", "1180,00", "", "", "", "", "", "", "", "", "", "", "", "T_EXTRATO", "EXT0000003798"]],
            status_updates={3634: "Transferido"},
        )

    assert client.append_attempts == 5
    assert sleeps == [1, 2, 4, 8]
    assert status_calls == []
