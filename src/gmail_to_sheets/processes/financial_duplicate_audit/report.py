"""Local reports for the read-only duplicate audit."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from .engine import normalize_amount
from .models import AuditFinding, AuditRun, Classification


def _finding_payload(finding: AuditFinding) -> dict[str, Any]:
    return {
        "row": finding.occurrence.row_number,
        "contaordem": finding.occurrence.row,
        "classification": finding.classification.value,
        "reason": finding.reason,
        "source_sheet": finding.source_sheet,
        "source_rows": list(finding.source_rows),
        "differences": finding.differences,
        "evidence": finding.evidence,
    }


def _potential_duplicate_impact(run: AuditRun) -> Decimal:
    by_source: dict[tuple[str | None, tuple[int, ...]], list[AuditFinding]] = defaultdict(list)
    for finding in run.findings:
        if finding.classification is Classification.POSSIBLE_DUPLICATE:
            by_source[(finding.source_sheet, finding.source_rows)].append(finding)
    impact = Decimal("0")
    for findings in by_source.values():
        if len(findings) > 1:
            amount = normalize_amount(findings[0].occurrence.row.get("IMPORTÂNCIA"))
            impact += abs(amount) * (len(findings) - 1)
    return impact


def build_payload(run: AuditRun) -> dict[str, Any]:
    findings_by_row = {finding.occurrence.row_number: finding for finding in run.findings}
    groups = []
    for group in run.groups:
        groups.append(
            {
                "movement_type": group.movement_type,
                "amount": str(group.amount),
                "occurrences": [
                    _finding_payload(findings_by_row[occurrence.row_number])
                    for occurrence in group.occurrences
                ],
            }
        )
    summary = Counter(finding.classification.value for finding in run.findings)
    return {
        "period": f"{run.year:04d}-{run.month:02d}",
        "read_only": True,
        "total_rows": run.total_rows,
        "period_rows": run.period_rows,
        "repeated_groups": len(run.groups),
        "summary": dict(sorted(summary.items())),
        "potential_duplicate_impact": str(_potential_duplicate_impact(run)),
        "invalid_dates": [{"row": row, "value": value} for row, value in run.invalid_dates],
        "invalid_amounts": [{"row": row, "value": value} for row, value in run.invalid_amounts],
        "source_sheets": list(run.source_sheets),
        "groups": groups,
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Auditoria financeira de duplicados — {payload['period']}",
        "",
        f"- Linhas CONTAORDEM: {payload['total_rows']}",
        f"- Linhas no período: {payload['period_rows']}",
        f"- Grupos repetidos: {payload['repeated_groups']}",
        f"- Impacto potencial: {payload['potential_duplicate_impact']}",
        "",
    ]
    current_type = None
    for group in payload["groups"]:
        if group["movement_type"] != current_type:
            current_type = group["movement_type"]
            lines.extend([f"## {current_type}", ""])
        lines.extend([f"### {group['amount']}", ""])
        for item in group["occurrences"]:
            lines.append(
                f"- Linha {item['row']}: **{item['classification']}** — {item['reason']}"
            )
        lines.append("")
    return "\n".join(lines)


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def write_reports(run: AuditRun, output_dir: Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    payload = build_payload(run)
    plan = {
        "period": payload["period"],
        "authorized": False,
        "items": [
            item
            for group in payload["groups"]
            for item in group["occurrences"]
            if item["classification"] != Classification.VALIDATED.value
        ],
    }
    paths = {
        "json": output_dir / "audit.json",
        "markdown": output_dir / "audit.md",
        "plan": output_dir / "correction_plan.json",
    }
    _write_atomic(paths["json"], json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
    _write_atomic(paths["markdown"], _markdown(payload))
    _write_atomic(paths["plan"], json.dumps(plan, ensure_ascii=False, indent=2, default=str) + "\n")
    return paths
