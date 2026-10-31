"""Pure selection and grouping rules for the duplicate audit."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import Occurrence, RepeatedAmountGroup


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
