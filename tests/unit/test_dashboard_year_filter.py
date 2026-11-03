import datetime as dt
import io
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard"))

from year_filter import filter_xlsx  # noqa: E402


def _xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "CONTAORDEM"
    ws.append(["Data Mov.", "IMPORTÂNCIA"])
    ws.append([dt.datetime(2025, 12, 31), 10.0])
    ws.append(["15/01/2026", 20.0])
    ws.append([dt.datetime(2026, 2, 1), 30.0])
    ws.append([None, 40.0])
    ws["A4"].number_format = "dd/MM/yyyy"
    wb.create_sheet("CONSTANTES").append(["CONTA", "TYPE_CC"])
    wb.create_sheet("SECRETA").append(["DATA", "X"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_drops_older_rows_and_unlisted_sheets() -> None:
    out = load_workbook(io.BytesIO(filter_xlsx(_xlsx(), 2026, {"CONTAORDEM", "CONSTANTES"})))
    assert out.sheetnames == ["CONTAORDEM", "CONSTANTES"]
    rows = list(out["CONTAORDEM"].iter_rows(values_only=True))
    assert [r[1] for r in rows[1:]] == [20.0, 30.0, 40.0]  # 2025 dropped, undated kept
    assert out["CONTAORDEM"]["A3"].number_format == "dd/MM/yyyy"


def test_keeps_all_sheets_when_no_list() -> None:
    out = load_workbook(io.BytesIO(filter_xlsx(_xlsx(), 2026)))
    assert "SECRETA" in out.sheetnames
