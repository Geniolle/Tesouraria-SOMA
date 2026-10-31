from decimal import Decimal

import pytest

from src.gmail_to_sheets.processes.financial_duplicate_audit.engine import (
    group_repeated_amounts,
    normalize_amount,
    select_period_rows,
)
from src.gmail_to_sheets.processes.financial_duplicate_audit.models import Classification


def test_normalize_amount_accepts_portuguese_money() -> None:
    assert normalize_amount("1.234,56 €") == Decimal("1234.56")
    assert normalize_amount("-42,10") == Decimal("-42.10")


@pytest.mark.parametrize("value", ["", None, "abc"])
def test_normalize_amount_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="invalid amount"):
        normalize_amount(value)


def test_select_period_rows_keeps_all_statuses_and_reports_invalid_dates() -> None:
    rows = [
        (2, {"DATA MOV.": "01/10/2026", "SOMA": "VALIDADO"}),
        (3, {"DATA MOV.": "31/10/2026", "SOMA": ""}),
        (4, {"DATA MOV.": "01/11/2026", "SOMA": ""}),
        (5, {"DATA MOV.": "not-a-date", "SOMA": ""}),
    ]

    selected, invalid = select_period_rows(rows, year=2026, month=10)

    assert [row_number for row_number, _ in selected] == [2, 3]
    assert invalid == [(5, "not-a-date")]


def test_group_repeated_amounts_separates_types_and_sorts_amount_descending() -> None:
    rows = [
        (2, {"TIPO": "Entrada", "IMPORTÂNCIA": "10,00"}),
        (3, {"TIPO": "Entrada", "IMPORTÂNCIA": "10.00"}),
        (4, {"TIPO": "Entrada", "IMPORTÂNCIA": "20,00"}),
        (5, {"TIPO": "Entrada", "IMPORTÂNCIA": "20,00"}),
        (6, {"TIPO": "Saída", "IMPORTÂNCIA": "20,00"}),
        (7, {"TIPO": "Saída", "IMPORTÂNCIA": "20,00"}),
    ]

    groups, invalid = group_repeated_amounts(rows)

    assert [(group.movement_type, group.amount) for group in groups] == [
        ("Entrada", Decimal("20.00")),
        ("Entrada", Decimal("10.00")),
        ("Saída", Decimal("20.00")),
    ]
    assert [[item.row_number for item in group.occurrences] for group in groups] == [
        [4, 5],
        [2, 3],
        [6, 7],
    ]
    assert invalid == []


def test_classifications_are_stable_report_values() -> None:
    assert [item.value for item in Classification] == [
        "VALIDADO",
        "POSSÍVEL DUPLICADO",
        "DIVERGÊNCIA DE PERÍODO",
        "DIVERGÊNCIA DE VALOR",
        "EM FALTA",
        "INCONCLUSIVO",
    ]
