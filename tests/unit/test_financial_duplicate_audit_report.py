import json
from decimal import Decimal

from src.gmail_to_sheets.processes.financial_duplicate_audit.models import (
    AuditFinding,
    AuditRun,
    Classification,
    Occurrence,
    RepeatedAmountGroup,
)
from src.gmail_to_sheets.processes.financial_duplicate_audit.report import write_reports


def _run() -> AuditRun:
    first = Occurrence(2, {"TIPO": "Entrada", "IMPORTÂNCIA": "100,00", "ID_INTERNO": "E1"})
    second = Occurrence(3, {"TIPO": "Entrada", "IMPORTÂNCIA": "100,00", "ID_INTERNO": "E1"})
    group = RepeatedAmountGroup("Entrada", Decimal("100.00"), (first, second))
    findings = tuple(
        AuditFinding(
            occurrence,
            Classification.POSSIBLE_DUPLICATE,
            "mesma origem",
            "T_EXTRATO",
            (20,),
        )
        for occurrence in (first, second)
    )
    return AuditRun(2026, 10, 10, 2, (group,), findings)


def test_write_reports_creates_structured_json_markdown_and_separate_plan(tmp_path) -> None:
    paths = write_reports(_run(), tmp_path)

    audit = json.loads(paths["json"].read_text(encoding="utf-8"))
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert audit["period"] == "2026-10"
    assert audit["summary"]["POSSÍVEL DUPLICADO"] == 2
    assert audit["potential_duplicate_impact"] == "100.00"
    assert audit["groups"][0]["movement_type"] == "Entrada"
    assert audit["groups"][0]["amount"] == "100.00"
    assert plan["authorized"] is False
    assert len(plan["items"]) == 2
    assert "# Auditoria financeira de duplicados — 2026-10" in markdown
    assert "## Entrada" in markdown
    assert "### 100.00" in markdown


def test_reports_do_not_include_credentials_from_unrelated_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", "private-secret")
    paths = write_reports(_run(), tmp_path)
    combined = "".join(path.read_text(encoding="utf-8") for path in paths.values())
    assert "private-secret" not in combined


def test_potential_impact_accepts_portuguese_thousands(tmp_path) -> None:
    run = _run()
    occurrences = tuple(
        Occurrence(item.row_number, {**item.row, "IMPORTÂNCIA": "1.100,00"})
        for item in run.groups[0].occurrences
    )
    group = RepeatedAmountGroup("Entrada", Decimal("1100.00"), occurrences)
    findings = tuple(
        AuditFinding(item, Classification.POSSIBLE_DUPLICATE, "mesma origem", "T_EXTRATO", (20,))
        for item in occurrences
    )
    changed = AuditRun(2026, 10, 10, 2, (group,), findings)
    paths = write_reports(changed, tmp_path)
    audit = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert audit["potential_duplicate_impact"] == "1100.00"
