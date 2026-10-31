"""Pure selection and grouping rules for the duplicate audit."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import AuditFinding, Classification, Occurrence, RepeatedAmountGroup


def normalize_amount(value: object) -> Decimal:
    text = str(value or "").strip().replace("€", "").replace(" ", "")
    if not text:
        raise ValueError(f"invalid amount: {value!r}")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc


def parse_sheet_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {value!r}")


def select_period_rows(
    rows: list[tuple[int, dict[str, Any]]], *, year: int, month: int
) -> tuple[list[tuple[int, dict[str, Any]]], list[tuple[int, object]]]:
    selected: list[tuple[int, dict[str, Any]]] = []
    invalid: list[tuple[int, object]] = []
    for row_number, row in rows:
        raw_date = row.get("DATA MOV.")
        try:
            movement_date = parse_sheet_date(raw_date)
        except ValueError:
            invalid.append((row_number, raw_date))
            continue
        if movement_date.year == year and movement_date.month == month:
            selected.append((row_number, row))
    return selected, invalid


def group_repeated_amounts(
    rows: list[tuple[int, dict[str, Any]]],
) -> tuple[list[RepeatedAmountGroup], list[tuple[int, object]]]:
    grouped: dict[tuple[str, Decimal], list[Occurrence]] = defaultdict(list)
    invalid: list[tuple[int, object]] = []
    for row_number, row in rows:
        try:
            amount = normalize_amount(row.get("IMPORTÂNCIA"))
        except ValueError:
            invalid.append((row_number, row.get("IMPORTÂNCIA")))
            continue
        movement_type = str(row.get("TIPO") or "").strip()
        grouped[(movement_type, amount)].append(Occurrence(row_number, row))

    groups = [
        RepeatedAmountGroup(movement_type, amount, tuple(occurrences))
        for (movement_type, amount), occurrences in grouped.items()
        if len(occurrences) > 1
    ]
    groups.sort(key=lambda item: (item.movement_type, -item.amount))
    return groups, invalid


def _fold(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def audit_group(
    group: RepeatedAmountGroup,
    sources: dict[str, list[tuple[int, dict[str, Any]]]],
) -> list[AuditFinding]:
    from .origins import ORIGIN_SPECS, canonicalize_source

    findings: list[AuditFinding] = []
    for occurrence in group.occurrences:
        process = str(occurrence.row.get("PROCESSO") or "").strip().upper()
        identifier = str(occurrence.row.get("ID_INTERNO") or "").strip()
        spec = ORIGIN_SPECS.get(process)
        if spec is None:
            findings.append(AuditFinding(occurrence, Classification.INCONCLUSIVE, "processo desconhecido"))
            continue
        if not identifier:
            findings.append(AuditFinding(occurrence, Classification.INCONCLUSIVE, "ID_INTERNO vazio", spec.source_sheet))
            continue

        candidates = [
            (row_number, row)
            for row_number, row in sources.get(process, [])
            if str(row.get("ID_INTERNO") or "").strip() == identifier
        ]
        if not candidates:
            findings.append(AuditFinding(occurrence, Classification.MISSING, "origem não encontrada", spec.source_sheet))
            continue
        if len(candidates) != 1:
            findings.append(
                AuditFinding(
                    occurrence,
                    Classification.INCONCLUSIVE,
                    "origem ambígua",
                    spec.source_sheet,
                    tuple(row_number for row_number, _ in candidates),
                )
            )
            continue

        source_row_number, source_row = candidates[0]
        canonical = canonicalize_source(spec, source_row)
        differences: dict[str, dict[str, Any]] = {}
        try:
            target_amount = normalize_amount(occurrence.row.get("IMPORTÂNCIA"))
        except ValueError:
            target_amount = None
        if target_amount != canonical["IMPORTÂNCIA"]:
            differences["IMPORTÂNCIA"] = {
                "CONTAORDEM": occurrence.row.get("IMPORTÂNCIA"),
                "ORIGEM": canonical["IMPORTÂNCIA"],
            }
            classification = Classification.AMOUNT_DIVERGENCE
            reason = "valor divergente"
        else:
            target_date: date | None
            source_date: date | None
            try:
                target_date = parse_sheet_date(occurrence.row.get("DATA MOV."))
                source_date = parse_sheet_date(canonical["DATA MOV."])
            except ValueError:
                target_date = source_date = None
            if target_date is None or source_date is None:
                classification = Classification.INCONCLUSIVE
                reason = "data inválida"
            elif target_date != source_date:
                differences["DATA MOV."] = {
                    "CONTAORDEM": occurrence.row.get("DATA MOV."),
                    "ORIGEM": canonical["DATA MOV."],
                }
                classification = Classification.PERIOD_DIVERGENCE
                reason = "data ou período divergente"
            elif _fold(occurrence.row.get("DESCRIÇÃO")) != _fold(canonical["DESCRIÇÃO"]):
                differences["DESCRIÇÃO"] = {
                    "CONTAORDEM": occurrence.row.get("DESCRIÇÃO"),
                    "ORIGEM": canonical["DESCRIÇÃO"],
                }
                classification = Classification.INCONCLUSIVE
                reason = "descrição divergente"
            else:
                classification = Classification.VALIDATED
                reason = "origem única e campos coerentes"
        findings.append(
            AuditFinding(
                occurrence,
                classification,
                reason,
                spec.source_sheet,
                (source_row_number,),
                differences,
                {
                    "DATA VALOR": canonical.get("DATA VALOR"),
                    "PERÍODO EXTRATO": canonical.get("PERÍODO EXTRATO"),
                    "NÚMERO EXTRATO": canonical.get("NÚMERO EXTRATO"),
                },
            )
        )

    identities: dict[tuple[str | None, tuple[int, ...]], list[int]] = defaultdict(list)
    for index, finding in enumerate(findings):
        if finding.classification is Classification.VALIDATED:
            identities[(finding.source_sheet, finding.source_rows)].append(index)
    for indexes in identities.values():
        if len(indexes) > 1:
            for index in indexes:
                findings[index] = replace(
                    findings[index],
                    classification=Classification.POSSIBLE_DUPLICATE,
                    reason="várias linhas CONTAORDEM apontam para a mesma origem",
                )
    return findings
