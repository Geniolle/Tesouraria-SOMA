"""Domain models for the read-only duplicate audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class Classification(str, Enum):
    VALIDATED = "VALIDADO"
    POSSIBLE_DUPLICATE = "POSSÍVEL DUPLICADO"
    PERIOD_DIVERGENCE = "DIVERGÊNCIA DE PERÍODO"
    AMOUNT_DIVERGENCE = "DIVERGÊNCIA DE VALOR"
    MISSING = "EM FALTA"
    INCONCLUSIVE = "INCONCLUSIVO"


@dataclass(frozen=True)
class Occurrence:
    row_number: int
    row: dict[str, Any]


@dataclass(frozen=True)
class RepeatedAmountGroup:
    movement_type: str
    amount: Decimal
    occurrences: tuple[Occurrence, ...]


@dataclass(frozen=True)
class AuditFinding:
    occurrence: Occurrence
    classification: Classification
    reason: str
    source_sheet: str | None = None
    source_rows: tuple[int, ...] = ()
    differences: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditRun:
    year: int
    month: int
    total_rows: int
    period_rows: int
    groups: tuple[RepeatedAmountGroup, ...]
    findings: tuple[AuditFinding, ...]
    invalid_dates: tuple[tuple[int, object], ...] = ()
    invalid_amounts: tuple[tuple[int, object], ...] = ()
    source_sheets: tuple[str, ...] = ()

